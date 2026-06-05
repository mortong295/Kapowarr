# -*- coding: utf-8 -*-

from asyncio import run
from datetime import datetime, timedelta
from io import BytesIO
from os.path import isdir
from typing import Any, Dict, List, Tuple, Type, Union

from flask import Blueprint, request, send_file

from backend.base.custom_exceptions import (InvalidKeyValue,
                                            KeyNotFound, TaskNotFound)
from backend.base.definitions import (BlocklistReason, BlocklistReasonID,
                                      Constants, CredentialData, CredentialSource,
                                      DownloadType, DownloadSource, FileMatch,
                                      KapowarrException, LibraryFilter,
                                      LibrarySorting, MonitorScheme,
                                      SpecialVersion, StartType, VolumeData)
from backend.base.helpers import hash_credential
from backend.base.logging import LOGGER, get_log_file_contents
from backend.features.download_queue import (DownloadHandler,
                                             delete_download_history,
                                             get_download_history)
from backend.features.library_import import (import_library,
                                             propose_library_import)
from backend.features.mass_edit import run_mass_editor_action
from backend.features.search import manual_search
from backend.features.tasks import (Task, TaskHandler,
                                    delete_task_history, get_task_history,
                                    get_task_planning, task_library)
from backend.implementations.arr_features import (comicinfo_xml,
                                                  delete_profile,
                                                  delete_provider,
                                                  delete_pull_list_item,
                                                  delete_story_arc,
                                                  get_cutoff_unmet_issues,
                                                  get_default_profile_id,
                                                  get_profile, get_profiles,
                                                  get_provider,
                                                  get_providers,
                                                  get_calendar_pull_list,
                                                  get_pull_list,
                                                  get_story_arc,
                                                  get_story_arc_missing,
                                                  get_story_arcs,
                                                  save_profile,
                                                  save_provider,
                                                  save_pull_list_item,
                                                  save_story_arc,
                                                  series_json,
                                                  sync_import_list,
                                                  test_provider,
                                                  write_comicinfo_xml,
                                                  write_series_json,
                                                  write_volume_metadata)
from backend.implementations.blocklist import (add_to_blocklist,
                                               delete_blocklist,
                                               delete_blocklist_entry,
                                               get_blocklist,
                                               get_blocklist_entry)
from backend.implementations.comicvine import ComicVine
from backend.implementations.conversion import preview_mass_convert
from backend.implementations.converters import ConvertersManager
from backend.implementations.credentials import Credentials
from backend.implementations.external_clients import ExternalClients
from backend.implementations.external_indexers import ExternalIndexers
from backend.implementations.file_matching import (get_file_matching,
                                                   set_file_matching)
from backend.implementations.mylar_import import (apply_mylar_export,
                                                  parse_mylar_export)
from backend.implementations.naming import (generate_volume_folder_name,
                                            preview_mass_rename)
from backend.implementations.remote_mapping import RemoteMappings
from backend.implementations.root_folders import RootFolders
from backend.implementations.volumes import Library, delete_issue_file
from backend.internals.db import get_db
from backend.internals.db_models import FilesDB
from backend.internals.server import Server, StartTypeHandlers
from backend.internals.settings import Settings, get_about_data

api = Blueprint('api', __name__)


def return_api(
    result: Any,
    error: Union[str, None] = None,
    code: int = 200
) -> Tuple[Dict[str, Any], int]:
    return {'error': error, 'result': result}, code


def error_handler(method) -> Any:
    """Used as decodator. Catches the errors that can occur in the endpoint and returns the correct api error
    """
    def wrapper(*args, **kwargs):
        try:
            return method(*args, **kwargs)

        except KapowarrException as e:
            return return_api(**e.api_response)

    wrapper.__name__ = method.__name__
    return wrapper


def extract_key(request, key: str, check_existence: bool = True) -> Any:
    """Extract and format a value of a parameter from a request

    Args:
        request (Request): The request from which to get the values.
        key (str): The key of which to get and format the value.
        check_existence (bool, optional): Require the key to be given in the request. Defaults to True.

    Raises:
        KeyNotFound: The key is not found in the request.
        InvalidKeyValue: The value of a key is invalid.
        TaskNotFound: The task was not found

    Returns:
        Any: The formatted value of the key.
    """
    value: Any = request.values.get(key)
    if check_existence and value is None:
        raise KeyNotFound(key)

    if value is not None:
        # Check value
        if key in ('volume_id', 'issue_id'):
            try:
                value = int(value)
                if key == 'volume_id':
                    Library.get_volume(value)
                else:
                    Library.get_issue(value)
            except (ValueError, TypeError):
                raise InvalidKeyValue(key, value)

        elif key == 'cmd':
            task = task_library.get(value)
            if task is None:
                raise TaskNotFound(value)
            value = task

        elif key == 'api_key':
            if not value or value != Settings().sv.api_key:
                raise InvalidKeyValue(key, value)

        elif key == 'sort':
            try:
                value = LibrarySorting[value.upper()]
            except KeyError:
                raise InvalidKeyValue(key, value)

        elif key == 'filter':
            try:
                value = LibraryFilter[value.upper()] if value else None
            except KeyError:
                raise InvalidKeyValue(key, value)

        elif key in (
            'root_folder_id', 'root_folder', 'quality_profile_id',
            'offset', 'limit', 'index'
        ):
            try:
                value = int(value)
            except (ValueError, TypeError):
                raise InvalidKeyValue(key, value)

        elif key in ('monitor', 'delete_folder', 'rename_files', 'only_english',
                    'limit_parent_folder', 'force_match'):
            if value == 'true':
                value = True
            elif value == 'false':
                value = False
            else:
                raise InvalidKeyValue(key, value)

        elif key in ('query', 'folder_filter'):
            if not value:
                raise InvalidKeyValue(key, value)

    else:
        # Default value
        if key == 'sort':
            value = LibrarySorting.TITLE

        elif key == 'filter':
            value = None

        elif key == 'monitor':
            value = True

        elif key == 'delete_folder':
            value = False

        elif key == 'offset':
            value = 0

        elif key == 'rename_files':
            value = False

        elif key == 'limit':
            value = 20

        elif key == 'only_english':
            value = True

        elif key == 'limit_parent_folder':
            value = False

        elif key == 'force_match':
            value = False

    return value

# =====================
# Authentication function and endpoints
# =====================


def auth(method):
    """Used as decorator and, if applied to route, restricts the route to authorized users only
    """
    def wrapper(*args, **kwargs):
        if not request.path.endswith('/cover'):
            LOGGER.debug(f'{request.method} {request.path}')

        try:
            extract_key(request, 'api_key')
        except (KeyNotFound, InvalidKeyValue):
            ip = request.environ.get(
                'HTTP_X_FORWARDED_FOR',
                request.remote_addr
            )
            LOGGER.warning(f'Unauthorised request from {ip}')
            return return_api({}, 'ApiKeyInvalid', 401)

        StartTypeHandlers.diffuse_timer(StartType.RESTART_HOSTING_CHANGES)

        result = method(*args, **kwargs)

        if result[1] > 300:
            LOGGER.debug(
                f'{request.method} {request.path} {result[1]} {result[0]}')

        return result

    wrapper.__name__ = method.__name__
    return wrapper


@api.route('/auth', methods=['POST'])
def api_auth():
    settings = Settings().get_settings()

    ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)

    if settings.auth_password:
        username_correct = True
        if settings.auth_username:
            given_username = request.get_json().get('username') or ''
            hashed_username = hash_credential(
                settings.auth_salt,
                given_username
            )
            username_correct = hashed_username == settings.auth_username

        given_password = request.get_json().get('password') or ''
        hashed_password = hash_credential(
            settings.auth_salt,
            given_password
        )
        password_correct = hashed_password == settings.auth_password

        if not (username_correct and password_correct):
            LOGGER.warning(f'Login attempt failed from {ip}')
            return return_api({}, 'PasswordInvalid', 401)

    LOGGER.info(f'Login attempt successful from {ip}')
    return return_api({'api_key': settings.api_key})


@api.route('/auth/check', methods=['POST'])
@error_handler
@auth
def api_auth_check():
    return return_api({})


@api.route('/public', methods=['GET'])
@error_handler
def api_public():
    settings = Settings().get_settings()

    if settings.auth_username and settings.auth_password:
        authentication_method = 2
    elif settings.auth_password:
        authentication_method = 1
    else:
        authentication_method = 0

    result = {
        'authentication_method': authentication_method
    }

    return return_api(result)


# =====================
# Tasks
# =====================
@api.route('/system/about', methods=['GET'])
@error_handler
@auth
def api_about():
    return return_api(get_about_data())


def _system_health() -> Dict[str, Any]:
    settings = Settings().sv
    root_folders = RootFolders().get_folder_list()
    clients = ExternalClients.get_clients()
    providers = {
        feature: get_providers(feature)
        for feature in ('indexers', 'connections', 'importlists')
    }
    enabled_indexers = [
        provider
        for provider in providers['indexers']
        if provider.get('enabled')
    ]
    enabled_connections = [
        provider
        for provider in providers['connections']
        if provider.get('enabled')
    ]
    enabled_importlists = [
        provider
        for provider in providers['importlists']
        if provider.get('enabled')
    ]
    download_types = {
        'torrent': len([
            client
            for client in clients
            if client.get('download_type') == DownloadType.TORRENT.value
        ]),
        'usenet': len([
            client
            for client in clients
            if client.get('download_type') == DownloadType.USENET.value
        ])
    }

    checks: List[Dict[str, str]] = []

    def add_check(
        key: str,
        status: str,
        message: str,
        action: str = ''
    ) -> None:
        checks.append({
            'key': key,
            'status': status,
            'message': message,
            'action': action
        })

    add_check(
        'comicvine_api_key',
        'ok' if settings.comicvine_api_key else 'warning',
        (
            'ComicVine API key is configured.'
            if settings.comicvine_api_key else
            'ComicVine API key is missing; metadata refresh will be limited.'
        ),
        'Add a ComicVine API key in Settings.'
    )
    add_check(
        'root_folders',
        'ok' if root_folders else 'error',
        (
            f'{len(root_folders)} root folder(s) configured.'
            if root_folders else
            'No root folders are configured.'
        ),
        'Add a library root folder.'
    )
    add_check(
        'download_folder',
        'ok' if isdir(settings.download_folder) else 'warning',
        (
            'Download folder exists.'
            if isdir(settings.download_folder) else
            'Download folder does not exist yet.'
        ),
        'Create or correct the download folder path.'
    )
    add_check(
        'indexers',
        'ok' if enabled_indexers else 'warning',
        f'{len(enabled_indexers)} enabled indexer provider(s).',
        'Enable at least one indexer provider.'
    )
    add_check(
        'download_clients',
        'ok' if clients else 'warning',
        (
            f"{len(clients)} download client(s) configured "
            f"({download_types['torrent']} torrent, "
            f"{download_types['usenet']} usenet)."
        ),
        'Add a torrent or Usenet download client.'
    )
    add_check(
        'connections',
        'ok' if enabled_connections else 'info',
        f'{len(enabled_connections)} enabled connection(s).',
        'Enable Plex, Jellyfin, or notification connections.'
    )
    add_check(
        'importlists',
        'ok' if enabled_importlists else 'info',
        f'{len(enabled_importlists)} enabled import list(s).',
        'Enable pull-list or migration import providers.'
    )

    status_order = {'ok': 0, 'info': 0, 'warning': 1, 'error': 2}
    worst = max(status_order[check['status']] for check in checks)
    status = 'error' if worst == 2 else 'warning' if worst == 1 else 'ok'

    return {
        'status': status,
        'checks': checks,
        'counts': {
            'root_folders': len(root_folders),
            'download_clients': len(clients),
            'enabled_indexers': len(enabled_indexers),
            'enabled_connections': len(enabled_connections),
            'enabled_importlists': len(enabled_importlists),
            'torrent_clients': download_types['torrent'],
            'usenet_clients': download_types['usenet']
        }
    }


@api.route('/system/health', methods=['GET'])
@error_handler
@auth
def api_system_health():
    return return_api(_system_health())


@api.route('/system/logs', methods=['GET'])
@error_handler
@auth
def api_logs():
    sio = get_log_file_contents()

    return send_file(
        BytesIO(sio.getvalue().encode('utf-8')),
        mimetype="application/octet-stream",
        download_name=f'Kapowarr_log_{datetime.now().strftime("%Y_%m_%d_%H_%M")}.txt'
    ), 200


@api.route('/system/tasks', methods=['GET', 'POST'])
@error_handler
@auth
def api_tasks():
    task_handler = TaskHandler()

    if request.method == 'GET':
        tasks = task_handler.get_all()
        return return_api(tasks)

    elif request.method == 'POST':
        data = request.get_json()
        if not isinstance(data, dict):
            raise InvalidKeyValue(value=data)

        task: Union[Type[Task], None] = task_library.get(data.get('cmd', ''))
        if not task:
            raise TaskNotFound(data.get('cmd', ''))

        kwargs = {}
        if task.action in (
            'refresh_and_scan', 'write_metadata',
            'auto_search', 'auto_search_issue',
            'mass_rename', 'mass_rename_issue',
            'mass_convert', 'mass_convert_issue'
        ):
            volume_id = data.get('volume_id')
            if not volume_id or not isinstance(volume_id, int):
                raise InvalidKeyValue('volume_id', volume_id)
            kwargs['volume_id'] = volume_id

        if task.action in (
            'auto_search_issue',
            'mass_rename_issue',
            'mass_convert_issue'
        ):
            issue_id = data.get('issue_id')
            if not issue_id or not isinstance(issue_id, int):
                raise InvalidKeyValue('issue_id', issue_id)
            kwargs['issue_id'] = issue_id

        if task.action in (
            'mass_rename', 'mass_rename_issue',
            'mass_convert', 'mass_convert_issue'
        ):
            filepath_filter = data.get('filepath_filter')
            if not (
                filepath_filter is None
                or isinstance(filepath_filter, list)
            ):
                raise InvalidKeyValue('filepath_filter', filepath_filter)
            kwargs['filepath_filter'] = filepath_filter or []

        if task.action == 'update_all':
            allow_skipping = data.get('allow_skipping', True)
            if not isinstance(allow_skipping, bool):
                raise InvalidKeyValue('allow_skipping', allow_skipping)
            kwargs['allow_skipping'] = allow_skipping

        task_instance = task(**kwargs)
        result = task_handler.add(task_instance)
        return return_api({'id': result}, code=201)


@api.route('/system/tasks/history', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_task_history():
    if request.method == 'GET':
        offset = extract_key(request, 'offset', False)
        tasks = get_task_history(offset)
        return return_api(tasks)

    elif request.method == 'DELETE':
        delete_task_history()
        return return_api({})


@api.route('/system/tasks/planning', methods=['GET'])
@error_handler
@auth
def api_task_planning():
    result = get_task_planning()
    return return_api(result)


@api.route('/system/tasks/<int:task_id>', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_task(task_id: int):
    task_handler = TaskHandler()

    if request.method == 'GET':
        task = task_handler.get_one(task_id)
        return return_api(task)

    elif request.method == 'DELETE':
        task_handler.remove(task_id)
        return return_api({})


@api.route('/system/power/shutdown', methods=['POST'])
@error_handler
@auth
def api_shutdown():
    Server().shutdown()
    return return_api({})


@api.route('/system/power/restart', methods=['POST'])
@error_handler
@auth
def api_restart():
    Server().restart()
    return return_api({})

# =====================
# Settings
# =====================


@api.route('/settings', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_settings():
    settings = Settings()
    if request.method == 'GET':
        result = settings.get_public_settings().todict()
        return return_api(result)

    elif request.method == 'PUT':
        data = request.get_json()

        hosting_changes = any(
            s in data
            and data[s] is not None
            and data[s] != getattr(settings.sv, s)
            for s in ('host', 'port', 'url_base')
        )
        proxy_changes = any(
            s in data
            and data[s] != getattr(settings.sv, s)
            for s in (
                'proxy_type', 'proxy_host', 'proxy_port',
                'proxy_username', 'proxy_password', 'proxy_ignored_addresses'
            )
        )

        if hosting_changes:
            settings.backup_hosting_settings()

        settings.update(data, from_public=True)

        if hosting_changes:
            Server().restart(StartType.RESTART_HOSTING_CHANGES)
        elif proxy_changes:
            Server().restart()

        return return_api(settings.get_public_settings().todict())

    elif request.method == 'DELETE':
        data = request.get_json()

        reset_keys = data.get('reset_keys')
        if not (
            isinstance(reset_keys, list)
            and all((
                isinstance(k, str)
                for k in reset_keys
            ))
        ):
            raise InvalidKeyValue('reset_keys', reset_keys)

        hosting_changes = any(
            s in data
            and data[s] is not None
            and data[s] != getattr(settings.sv, s)
            for s in ('host', 'port', 'url_base')
        )
        proxy_changes = any(
            s in data
            and data[s] != getattr(settings.sv, s)
            for s in (
                'proxy_type', 'proxy_host', 'proxy_port',
                'proxy_username', 'proxy_password', 'proxy_ignored_addresses'
            )
        )

        if hosting_changes:
            settings.backup_hosting_settings()

        for reset_key in reset_keys:
            settings.reset(reset_key, from_public=True)

        if hosting_changes:
            Server().restart(StartType.RESTART_HOSTING_CHANGES)
        elif proxy_changes:
            Server().restart()

        return return_api(settings.get_public_settings().todict())


@api.route('/settings/api_key', methods=['POST'])
@error_handler
@auth
def api_settings_api_key():
    settings = Settings()
    settings.generate_api_key()
    return return_api(settings.get_public_settings().todict())


@api.route('/settings/availableformats', methods=['GET'])
@error_handler
@auth
def api_settings_available_formats():
    result = list(ConvertersManager.get_available_formats())
    return return_api(result)


@api.route('/rootfolder', methods=['GET', 'POST'])
@error_handler
@auth
def api_rootfolder():
    root_folders = RootFolders()

    if request.method == 'GET':
        result = [
            rf.todict()
            for rf in root_folders.get_all()
        ]
        return return_api(result)

    elif request.method == 'POST':
        data: dict = request.get_json()
        folder = data.get('folder')
        if folder is None:
            raise KeyNotFound('folder')
        root_folder = root_folders.add(folder).todict()
        return return_api(root_folder, code=201)


@api.route('/rootfolder/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_rootfolder_id(id: int):
    root_folders = RootFolders()

    if request.method == 'GET':
        root_folder = root_folders.get_one(id).todict()
        return return_api(root_folder)

    elif request.method == 'PUT':
        folder: Union[str, None] = request.get_json().get('folder')
        if not folder:
            raise KeyNotFound('folder')
        root_folders.rename(id, folder)
        return return_api({})

    elif request.method == 'DELETE':
        root_folders.delete(id)
        return return_api({})


@api.route('/remotemapping', methods=['GET', 'POST'])
@error_handler
@auth
def api_remote_mappings():
    remote_mappings = RemoteMappings

    if request.method == 'GET':
        return return_api(remote_mappings.get_all())

    elif request.method == 'POST':
        data: dict = request.get_json()

        external_download_client_id = data.get('external_download_client_id')
        remote_path = data.get('remote_path')
        local_path = data.get('local_path')

        if (
            not isinstance(external_download_client_id, int)
            or external_download_client_id < 1
        ):
            raise InvalidKeyValue(
                'external_download_client_id',
                external_download_client_id
            )

        if not isinstance(remote_path, str) or not remote_path:
            raise InvalidKeyValue('remote_path', remote_path)

        if not isinstance(local_path, str) or not local_path:
            raise InvalidKeyValue('local_path', local_path)

        result = remote_mappings.add(
            external_download_client_id,
            remote_path,
            local_path
        ).get()
        return return_api(result, code=201)


@api.route('/remotemapping/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_remote_mapping(id: int):
    remote_mapping = RemoteMappings.get_one(id)

    if request.method == 'GET':
        return return_api(remote_mapping.get())

    elif request.method == 'PUT':
        data: dict = request.get_json()

        external_download_client_id = data.get('external_download_client_id')
        remote_path = data.get('remote_path')
        local_path = data.get('local_path')

        if not (
            external_download_client_id is None
            or (
                isinstance(external_download_client_id, int)
                and external_download_client_id >= 1
            )
        ):
            raise InvalidKeyValue(
                'external_download_client_id',
                external_download_client_id
            )

        if not (
            remote_path is None
            or (
                isinstance(remote_path, str)
                and remote_path
            )
        ):
            raise InvalidKeyValue('remote_path', remote_path)

        if not (
            local_path is None
            or (
                isinstance(local_path, str)
                and local_path
            )
        ):
            raise InvalidKeyValue('local_path', local_path)

        result = remote_mapping.update(
            external_download_client_id,
            remote_path,
            local_path
        )
        return return_api(result, code=201)

    elif request.method == 'DELETE':
        remote_mapping.delete()
        return return_api({})


# =====================
# Arr-style UX foundation
# =====================

def _arr_feature_cards(feature: str) -> List[Dict[str, Any]]:
    feature_cards: Dict[str, List[Dict[str, Any]]] = {
        "profiles": [
            {
                "name": "Quality Profiles",
                "status": "planned",
                "description": (
                    "Define allowed comic formats, upgrade rules, "
                    "and cutoffs before automatic grabbing is enabled."
                )
            },
            {
                "name": "Custom Formats",
                "status": "planned",
                "description": (
                    "Score digital releases, scans, archive types, "
                    "languages, trusted groups, and metadata quality."
                )
            },
            {
                "name": "Metadata Profiles",
                "status": "planned",
                "description": (
                    "Control ComicInfo.xml, series.json, and archive "
                    "tagging behavior per volume or tag."
                )
            }
        ],
        "indexers": [
            {
                "name": "GetComics",
                "status": "available",
                "description": (
                    "Current Kapowarr search source for direct links, "
                    "mirrors, and GetComics torrent links."
                )
            },
            {
                "name": "Newznab/Torznab",
                "status": "planned",
                "description": (
                    "Add standard *arr-compatible indexers with "
                    "capabilities, priority, tags, and RSS sync."
                )
            },
            {
                "name": "Raw RSS",
                "status": "planned",
                "description": (
                    "Support custom comic feeds with parser rules and "
                    "release-decision scoring."
                )
            }
        ],
        "connections": [
            {
                "name": "Webhook",
                "status": "available",
                "description": (
                    "Notify other tools when comics are grabbed, "
                    "imported, failed, or updated."
                )
            },
            {
                "name": "Discord/Gotify",
                "status": "available",
                "description": "Send user-facing grab/import/failure notifications."
            },
            {
                "name": "Plex/Jellyfin",
                "status": "available",
                "description": (
                    "Refresh library applications after Kapowarr "
                    "imports or retags files."
                )
            }
        ],
        "importlists": [
            {
                "name": "ComicVine Lists",
                "status": "planned",
                "description": (
                    "Auto-add volumes from publishers, characters, "
                    "teams, story arcs, and curated lists."
                )
            },
            {
                "name": "Pull Lists",
                "status": "available",
                "description": (
                    "Surface weekly releases and let monitored volumes "
                    "grab matching upcoming issues."
                )
            },
            {
                "name": "Mylar Migration",
                "status": "planned",
                "description": (
                    "Import existing Mylar watchlists and apply "
                    "Kapowarr root folders, profiles, and tags."
                )
            }
        ]
    }
    return feature_cards[feature]


def _missing_issues(
    limit: int = 200,
    offset: int = 0,
    quality_profile_id: Union[int, None] = None
) -> List[Dict[str, Any]]:
    profile_filter = ''
    params: List[Any] = []
    if quality_profile_id is not None:
        profile_filter = 'AND v.quality_profile_id = ?'
        params.append(quality_profile_id)

    params.extend((limit, offset))
    return get_db().execute(f"""
        SELECT
            i.id AS issue_id,
            i.issue_number,
            i.title AS issue_title,
            i.date,
            i.monitored AS issue_monitored,
            v.id AS volume_id,
            v.title AS volume_title,
            v.year,
            v.publisher,
            v.volume_number,
            v.monitored AS volume_monitored,
            v.quality_profile_id,
            aqp.name AS quality_profile_name,
            'Missing monitored issue has no matched file.' AS decision
        FROM issues i
        INNER JOIN volumes v
            ON i.volume_id = v.id
        LEFT JOIN arr_quality_profiles aqp
            ON v.quality_profile_id = aqp.id
        LEFT JOIN issues_files if
            ON i.id = if.issue_id
        WHERE
            v.monitored = 1
            AND i.monitored = 1
            AND if.issue_id IS NULL
            {profile_filter}
        GROUP BY i.id
        ORDER BY
            CASE WHEN i.date IS NULL OR i.date = '' THEN 1 ELSE 0 END,
            i.date,
            v.title,
            i.calculated_issue_number
        LIMIT ? OFFSET ?;
        """,
        tuple(params)
    ).fetchalldict()


def _calendar_issues(days: int = 90, limit: int = 200) -> List[Dict[str, Any]]:
    start = datetime.utcnow().date().isoformat()
    end = (datetime.utcnow().date() + timedelta(days=days)).isoformat()
    return get_db().execute("""
        SELECT
            i.id AS issue_id,
            i.issue_number,
            i.title AS issue_title,
            i.date,
            i.monitored AS issue_monitored,
            COUNT(if.file_id) > 0 AS downloaded,
            v.id AS volume_id,
            v.title AS volume_title,
            v.year,
            v.publisher,
            v.volume_number,
            v.monitored AS volume_monitored
        FROM issues i
        INNER JOIN volumes v
            ON i.volume_id = v.id
        LEFT JOIN issues_files if
            ON i.id = if.issue_id
        WHERE
            i.date >= ?
            AND i.date <= ?
        GROUP BY i.id
        ORDER BY i.date, v.title, i.calculated_issue_number
        LIMIT ?;
        """,
        (start, end, limit)
    ).fetchalldict()


@api.route('/calendar', methods=['GET'])
@error_handler
@auth
def api_calendar():
    try:
        days = int(request.values.get('days', 90))
    except (TypeError, ValueError):
        raise InvalidKeyValue('days', request.values.get('days'))

    if days < 1 or days > 366:
        raise InvalidKeyValue('days', days)

    enabled_import_lists = [
        provider
        for provider in get_providers('importlists')
        if provider.get('enabled')
    ]

    return return_api({
        'items': _calendar_issues(days),
        'pull_list_items': get_calendar_pull_list(days),
        'pull_list': {
            'status': 'available',
            'sync_on_load': False,
            'enabled_providers': len(enabled_import_lists),
            'providers': [
                {
                    'id': provider.get('id'),
                    'name': provider.get('name'),
                    'implementation': provider.get('implementation'),
                    'last_sync': provider.get('last_sync')
                }
                for provider in enabled_import_lists
            ],
            'description': (
                'Weekly pull-list providers are synced into this calendar.'
            )
        }
    })


@api.route('/wanted/missing', methods=['GET'])
@error_handler
@auth
def api_wanted_missing():
    quality_profile_id = extract_key(
        request,
        'quality_profile_id',
        False
    )
    limit = extract_key(request, 'limit', False) or 50
    offset = extract_key(request, 'offset', False) or 0
    return return_api({
        'items': _missing_issues(
            limit=limit,
            offset=offset,
            quality_profile_id=quality_profile_id
        ),
        'cutoff_unmet': {
            'items': get_cutoff_unmet_issues(
                limit=limit,
                offset=offset,
                quality_profile_id=quality_profile_id
            )
        }
    })


@api.route('/wanted/cutoff-unmet', methods=['GET'])
@error_handler
@auth
def api_wanted_cutoff_unmet():
    quality_profile_id = extract_key(
        request,
        'quality_profile_id',
        False
    )
    limit = extract_key(request, 'limit', False) or 50
    offset = extract_key(request, 'offset', False) or 0
    return return_api({
        'items': get_cutoff_unmet_issues(
            limit=limit,
            offset=offset,
            quality_profile_id=quality_profile_id
        )
    })


@api.route('/profiles', methods=['GET', 'POST'])
@error_handler
@auth
def api_profiles():
    if request.method == 'GET':
        return return_api(get_profiles())

    elif request.method == 'POST':
        return return_api(save_profile(request.get_json()), code=201)


@api.route('/profiles/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_profile(id: int):
    if request.method == 'GET':
        return return_api(get_profile(id))

    elif request.method == 'PUT':
        return return_api(save_profile(request.get_json(), id))

    elif request.method == 'DELETE':
        delete_profile(id)
        return return_api({})


def _provider_endpoint(feature: str):
    if request.method == 'GET':
        return return_api(get_providers(feature))

    elif request.method == 'POST':
        return return_api(
            save_provider(feature, request.get_json()),
            code=201
        )


def _provider_item_endpoint(feature: str, id: int):
    if request.method == 'GET':
        return return_api(get_provider(feature, id))

    elif request.method == 'PUT':
        return return_api(save_provider(feature, request.get_json(), id))

    elif request.method == 'DELETE':
        delete_provider(feature, id)
        return return_api({})


@api.route('/indexers', methods=['GET', 'POST'])
@error_handler
@auth
def api_indexers():
    return _provider_endpoint('indexers')


@api.route('/indexers/test', methods=['POST'])
@error_handler
@auth
def api_indexer_test():
    return return_api(test_provider('indexers', request.get_json() or {}))


@api.route('/indexers/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_indexer(id: int):
    return _provider_item_endpoint('indexers', id)


@api.route('/connections', methods=['GET', 'POST'])
@error_handler
@auth
def api_connections():
    return _provider_endpoint('connections')


@api.route('/connections/test', methods=['POST'])
@error_handler
@auth
def api_connection_test():
    return return_api(test_provider('connections', request.get_json() or {}))


@api.route('/connections/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_connection(id: int):
    return _provider_item_endpoint('connections', id)


@api.route('/importlists', methods=['GET', 'POST'])
@error_handler
@auth
def api_import_lists():
    return _provider_endpoint('importlists')


@api.route('/importlists/test', methods=['POST'])
@error_handler
@auth
def api_import_list_test():
    return return_api(test_provider('importlists', request.get_json() or {}))


@api.route('/importlists/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_import_list(id: int):
    return _provider_item_endpoint('importlists', id)


@api.route('/importlists/<int:id>/sync', methods=['POST'])
@error_handler
@auth
def api_import_list_sync(id: int):
    return return_api(sync_import_list(id))


@api.route('/importlists/mylar/preview', methods=['POST'])
@error_handler
@auth
def api_mylar_import_preview():
    data = request.get_json()
    if isinstance(data, dict) and 'export' in data:
        data = data['export']
    return return_api(parse_mylar_export(data or {}))


@api.route('/importlists/mylar/apply', methods=['POST'])
@error_handler
@auth
def api_mylar_import_apply():
    payload = request.get_json()
    if not isinstance(payload, dict):
        raise InvalidKeyValue('body', payload)
    data = payload.get('export', payload)
    options = payload.get('options') if 'export' in payload else payload
    if not isinstance(options, dict):
        raise InvalidKeyValue('options', options)
    return return_api(apply_mylar_export(data or {}, options), code=201)


@api.route('/pulllist', methods=['GET', 'POST'])
@error_handler
@auth
def api_pull_list():
    if request.method == 'GET':
        return return_api(get_pull_list())

    elif request.method == 'POST':
        return return_api(save_pull_list_item(request.get_json()), code=201)


@api.route('/pulllist/<int:id>', methods=['DELETE'])
@error_handler
@auth
def api_pull_list_item(id: int):
    delete_pull_list_item(id)
    return return_api({})


@api.route('/storyarcs', methods=['GET', 'POST'])
@error_handler
@auth
def api_story_arcs():
    if request.method == 'GET':
        return return_api(get_story_arcs())

    elif request.method == 'POST':
        return return_api(save_story_arc(request.get_json()), code=201)


@api.route('/storyarcs/missing', methods=['GET'])
@error_handler
@auth
def api_story_arcs_missing():
    return return_api(get_story_arc_missing())


@api.route('/storyarcs/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_story_arc(id: int):
    if request.method == 'GET':
        return return_api(get_story_arc(id))

    elif request.method == 'PUT':
        return return_api(save_story_arc(request.get_json(), id))

    elif request.method == 'DELETE':
        delete_story_arc(id)
        return return_api({})


@api.route('/comicvine/storyarcs/search', methods=['GET'])
@error_handler
@auth
def api_comicvine_story_arc_search():
    query = extract_key(request, 'query')
    return return_api(run(ComicVine().search_story_arcs(query)))


@api.route('/comicvine/storyarcs/<int:id>/import', methods=['POST'])
@error_handler
@auth
def api_comicvine_story_arc_import(id: int):
    story_arc = run(ComicVine().fetch_story_arc(id))
    payload = {
        'title': story_arc['title'],
        'description': story_arc.get('description') or '',
        'comicvine_id': story_arc.get('comicvine_id'),
        'monitored': True,
        'issues': story_arc.get('issues') or []
    }
    return return_api(save_story_arc(payload), code=201)


@api.route('/volumes/<int:id>/metadata', methods=['POST'])
@error_handler
@auth
def api_volume_metadata(id: int):
    return return_api(write_volume_metadata(id), code=201)


@api.route('/volumes/<int:id>/metadata/comicinfo', methods=['GET', 'POST'])
@error_handler
@auth
def api_volume_comicinfo(id: int):
    issue_id = request.values.get('issue_id')
    if issue_id is not None:
        try:
            issue_id = int(issue_id)
        except (TypeError, ValueError):
            raise InvalidKeyValue('issue_id', issue_id)

    if request.method == 'GET':
        return return_api({'comicinfo': comicinfo_xml(id, issue_id)})

    elif request.method == 'POST':
        return return_api(write_comicinfo_xml(id, issue_id), code=201)


@api.route('/volumes/<int:id>/metadata/seriesjson', methods=['GET', 'POST'])
@error_handler
@auth
def api_volume_seriesjson(id: int):
    if request.method == 'GET':
        return return_api(series_json(id))

    elif request.method == 'POST':
        return return_api(write_series_json(id), code=201)


# =====================
# Library Import
# =====================
@api.route('/libraryimport', methods=['GET', 'POST'])
@error_handler
@auth
def api_library_import():
    if request.method == 'GET':
        folder_filter = extract_key(
            request,
            'folder_filter',
            check_existence=False
        )
        limit = extract_key(
            request,
            'limit',
            check_existence=False
        )
        only_english = extract_key(
            request,
            'only_english',
            check_existence=False
        )
        limit_parent_folder = extract_key(
            request,
            'limit_parent_folder',
            check_existence=False
        )
        result = propose_library_import(
            folder_filter,
            limit,
            limit_parent_folder,
            only_english
        )
        return return_api(result)

    elif request.method == 'POST':
        data = request.get_json()
        rename_files = extract_key(request, 'rename_files', False)

        if (
            not isinstance(data, list)
            or not all(
                isinstance(e, dict) and 'filepath' in e and 'id' in e
                for e in data
            )
        ):
            raise InvalidKeyValue

        import_library(data, rename_files)
        return return_api({}, code=201)

# =====================
# Library + Volumes
# =====================


@api.route('/volumes/search', methods=['GET', 'POST'])
@error_handler
@auth
def api_volumes_search():
    if request.method == 'GET':
        query = extract_key(request, 'query')
        search_results = run(ComicVine().search_volumes(query))
        for r in search_results:
            del r["cover"] # type: ignore
        return return_api(search_results)

    elif request.method == 'POST':
        data: Dict[str, Any] = request.get_json()
        for key in (
            'comicvine_id',
            'title', 'year', 'volume_number',
            'publisher'
        ):
            if key not in data:
                raise KeyNotFound(key)

        vd = VolumeData(
            id=0,
            comicvine_id=data['comicvine_id'],
            title=data['title'],
            alt_title=data['title'],
            year=data['year'],
            publisher=data['publisher'],
            volume_number=data['volume_number'],
            description="",
            site_url="",
            monitored=True,
            monitor_new_issues=True,
            quality_profile_id=get_default_profile_id(),
            root_folder=1,
            folder="",
            custom_folder=False,
            special_version=SpecialVersion(data.get('special_version')),
            special_version_locked=False,
            last_cv_fetch=0
        )

        folder = generate_volume_folder_name(vd)
        return return_api({'folder': folder})


@api.route('/volumes', methods=['GET', 'POST'])
@error_handler
@auth
def api_volumes():
    if request.method == 'GET':
        query = extract_key(request, 'query', False)
        sort = extract_key(request, 'sort', False)
        filter = extract_key(request, 'filter', False)
        quality_profile_id = extract_key(
            request,
            'quality_profile_id',
            False
        )
        if query:
            volumes = Library.search(query, sort, filter, quality_profile_id)
        else:
            volumes = Library.get_public_volumes(
                sort,
                filter,
                quality_profile_id
            )

        return return_api(volumes)

    elif request.method == 'POST':
        data: dict = request.get_json()

        comicvine_id = data.get('comicvine_id')
        if comicvine_id is None:
            raise KeyNotFound('comicvine_id')

        root_folder_id = data.get('root_folder_id')
        if root_folder_id is None:
            raise KeyNotFound('root_folder_id')

        monitor = data.get('monitor', True)
        if not isinstance(monitor, bool):
            raise InvalidKeyValue('monitor', monitor)

        monitoring_scheme = data.get('monitoring_scheme') or "all"
        try:
            monitoring_scheme = MonitorScheme(monitoring_scheme)
        except ValueError:
            raise InvalidKeyValue("monitoring_scheme", monitoring_scheme)

        monitor_new_issues = data.get('monitor_new_issues', True)
        if not isinstance(monitor_new_issues, bool):
            raise InvalidKeyValue('monitor_new_issues', monitor_new_issues)

        volume_folder = data.get('volume_folder') or None

        quality_profile_id = data.get('quality_profile_id')
        if quality_profile_id is None:
            quality_profile_id = get_default_profile_id()
        elif not isinstance(quality_profile_id, int):
            raise InvalidKeyValue('quality_profile_id', quality_profile_id)

        auto_search = data.get('auto_search', True)
        if not isinstance(auto_search, bool):
            raise InvalidKeyValue('auto_search', auto_search)

        special_version = data.get('special_version') or None
        if special_version == 'auto':
            sv = None
        else:
            try:
                sv = SpecialVersion(special_version)
            except ValueError:
                raise InvalidKeyValue('special_version', special_version)

        volume_id = Library.add(
            comicvine_id,
            root_folder_id,
            monitor,
            monitoring_scheme,
            monitor_new_issues,
            volume_folder,
            sv,
            auto_search,
            quality_profile_id
        )
        volume_info = Library.get_volume(volume_id).get_public_data()
        return return_api(volume_info, code=201)


@api.route('/volumes/stats', methods=['GET'])
@error_handler
@auth
def api_volumes_stats():
    result = Library.get_stats()
    return return_api(result)


@api.route('/volumes/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_volume(id: int):
    volume = Library.get_volume(id)

    if request.method == 'GET':
        volume_info = volume.get_public_data()
        return return_api(volume_info)

    elif request.method == 'PUT':
        edit_info: Dict[str, Any] = request.get_json()

        if 'root_folder' in edit_info:
            volume.change_root_folder(edit_info['root_folder'])

        if 'volume_folder' in edit_info:
            volume.change_volume_folder(edit_info['volume_folder'])

        if 'monitoring_scheme' in edit_info:
            try:
                monitoring_scheme = MonitorScheme(
                    edit_info['monitoring_scheme']
                )

            except ValueError:
                raise InvalidKeyValue(
                    'monitoring_scheme',
                    edit_info['monitoring_scheme']
                )

            volume.apply_monitor_scheme(monitoring_scheme)

        volume.update({
            k: v
            for k, v in edit_info.items()
            if k not in ('root_folder', 'volume_folder', 'monitoring_scheme')
        })
        return return_api(None)

    elif request.method == 'DELETE':
        delete_folder = extract_key(request, 'delete_folder')
        volume.delete(delete_folder=delete_folder)
        return return_api({})


@api.route('/volumes/<int:id>/cover', methods=['GET'])
@error_handler
@auth
def api_volume_cover(id: int):
    cover = Library.get_volume(id).get_cover()
    return send_file(
        cover,
        mimetype='image/jpeg'
    ), 200


@api.route('/issues/<int:id>', methods=['GET', 'PUT'])
@error_handler
@auth
def api_issues(id: int):
    issue = Library.get_issue(id)

    if request.method == 'GET':
        result = issue.get_data()
        return return_api(result)

    elif request.method == 'PUT':
        edit_info: dict = request.get_json()
        monitored = edit_info.get('monitored')
        if monitored is not None:
            issue.update({'monitored': monitored})

        result = issue.get_data()
        return return_api(result)


# =====================
# Manual File Match
# =====================
@api.route('/volumes/<int:id>/manualmatch', methods=['GET', 'PUT'])
@error_handler
@auth
def api_manual_match(id: int):
    Library.get_volume(id)

    if request.method == 'GET':
        result = get_file_matching(id)
        return return_api(result)

    elif request.method == 'PUT':
        file_matching_changes = request.get_json()
        if not isinstance(file_matching_changes, list):
            raise InvalidKeyValue('body', file_matching_changes)

        entry_types = FileMatch.__annotations__
        for entry in file_matching_changes:
            if not isinstance(entry, dict):
                raise InvalidKeyValue('body', file_matching_changes)
            if not all(
                key in entry_types
                and (
                    (
                        isinstance(value, list)
                        and all(isinstance(i_id, int) for i_id in value)
                    )
                    if entry_types[key] == List[int] else
                    isinstance(value, entry_types[key])
                )
                for key, value in entry.items()
            ):
                raise InvalidKeyValue('body', file_matching_changes)

        set_file_matching(id, file_matching_changes)

        return return_api({})


# =====================
# Renaming
# =====================
@api.route('/volumes/<int:id>/rename', methods=['GET'])
@error_handler
@auth
def api_rename(id: int):
    Library.get_volume(id)
    all_namings = preview_mass_rename(id)[0]
    only_renamings = {
        before: after
        for before, after in all_namings.items()
        if before != after
    }
    return return_api(only_renamings)


@api.route('/issues/<int:id>/rename', methods=['GET'])
@error_handler
@auth
def api_rename_issue(id: int):
    volume_id = Library.get_issue(id).get_data().volume_id
    all_namings = preview_mass_rename(volume_id, id)[0]
    only_renamings = {
        before: after
        for before, after in all_namings.items()
        if before != after
    }
    return return_api(only_renamings)

# =====================
# File Conversion
# =====================


@api.route('/volumes/<int:id>/convert', methods=['GET'])
@error_handler
@auth
def api_convert(id: int):
    Library.get_volume(id)
    result = preview_mass_convert(id)
    return return_api(result)


@api.route('/issues/<int:id>/convert', methods=['GET'])
@error_handler
@auth
def api_convert_issue(id: int):
    volume_id = Library.get_issue(id).get_data().volume_id
    result = preview_mass_convert(volume_id, id)
    return return_api(result)

# =====================
# Manual search + Download
# =====================


@api.route('/volumes/<int:id>/manualsearch', methods=['GET'])
@error_handler
@auth
def api_volume_manual_search(id: int):
    Library.get_volume(id)
    result = manual_search(id)
    return return_api(result)


def _download_request_data() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _download_queue_options(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: data[key]
        for key in (
            'download_type',
            'source_type',
            'source_name',
            'web_title'
        )
        if data.get(key) not in (None, '')
    }


@api.route('/volumes/<int:id>/download', methods=['POST'])
@error_handler
@auth
def api_volume_download(id: int):
    Library.get_volume(id)
    data = _download_request_data()
    link: str = data.get('link') or extract_key(request, 'link')
    force_match = (
        bool(data['force_match'])
        if 'force_match' in data else
        extract_key(request, 'force_match')
    )
    result = run(DownloadHandler().add(
        link,
        id,
        force_match=force_match,
        **_download_queue_options(data)
    ))
    return return_api(
        {
            'result': (result or (None,))[0],
            'fail_reason': result[1].value if result[1] else result[1]
        },
        code=201
    )


@api.route('/issues/<int:id>/manualsearch', methods=['GET'])
@error_handler
@auth
def api_issue_manual_search(id: int):
    volume_id = Library.get_issue(id).get_data().volume_id
    result = manual_search(
        volume_id,
        id
    )
    return return_api(result)


@api.route('/issues/<int:id>/download', methods=['POST'])
@error_handler
@auth
def api_issue_download(id: int):
    volume_id = Library.get_issue(id).get_data().volume_id
    data = _download_request_data()
    link = data.get('link') or extract_key(request, 'link')
    force_match = (
        bool(data['force_match'])
        if 'force_match' in data else
        extract_key(request, 'force_match')
    )
    result = run(DownloadHandler().add(
        link,
        volume_id,
        id,
        force_match=force_match,
        **_download_queue_options(data)
    ))
    return return_api(
        {
            'result': result[0],
            'fail_reason': result[1].value if result[1] else result[1]
        },
        code=201
    )


@api.route('/activity/queue', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_downloads():
    download_handler = DownloadHandler()

    if request.method == 'GET':
        result = download_handler.get_all()
        return return_api(result)

    elif request.method == 'DELETE':
        download_handler.remove_all()
        return return_api({})


@api.route(
    '/activity/queue/<int:download_id>',
    methods=['GET', 'PUT', 'DELETE']
)
@error_handler
@auth
def api_delete_download(download_id: int):
    download_handler = DownloadHandler()

    if request.method == 'GET':
        result = download_handler.get_one(download_id).as_dict()
        return return_api(result)

    elif request.method == 'PUT':
        index: int = extract_key(request, 'index')
        download_handler.set_queue_location(download_id, index)
        return return_api({})

    elif request.method == 'DELETE':
        data: Dict[str, Any] = request.get_json(silent=True) or {}
        blocklist = data.get('blocklist', False)
        if not isinstance(blocklist, bool):
            raise InvalidKeyValue('blocklist', blocklist)

        download_handler.remove(download_id, blocklist)
        return return_api({})


@api.route('/activity/history', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_download_history():
    if request.method == 'GET':
        volume_id: int = extract_key(request, 'volume_id', False)
        issue_id: int = extract_key(request, 'issue_id', False)
        offset: int = extract_key(request, 'offset', False)
        result = get_download_history(
            volume_id, issue_id,
            offset
        )
        return return_api(result)

    elif request.method == 'DELETE':
        delete_download_history()
        return return_api({})


@api.route('/activity/folder', methods=['DELETE'])
@error_handler
@auth
def api_empty_download_folder():
    DownloadHandler().empty_download_folder()
    return return_api({})

# =====================
# Blocklist
# =====================


@api.route('/blocklist', methods=['GET', 'POST', 'DELETE'])
@error_handler
@auth
def api_blocklist():
    if request.method == 'GET':
        offset = extract_key(request, 'offset', False)

        blocklist = get_blocklist(offset)
        result = [
            b.todict()
            for b in blocklist
        ]
        return return_api(result)

    elif request.method == 'POST':
        data = request.get_json()
        if not isinstance(data, dict):
            raise InvalidKeyValue(value=data)

        web_link = data.get('web_link')
        if not (web_link and isinstance(web_link, str)):
            raise InvalidKeyValue('web_link', web_link)

        web_title = data.get('web_title')
        if not (
            web_title is None
            or web_title
                and isinstance(web_title, str)
        ):
            raise InvalidKeyValue('web_title', web_title)

        web_sub_title = data.get('web_sub_title')
        if not (
            web_sub_title is None
            or web_sub_title
                and isinstance(web_sub_title, str)
        ):
            raise InvalidKeyValue('web_sub_title', web_sub_title)

        download_link = data.get('download_link')
        if not (
            download_link is None
            or download_link
                and isinstance(download_link, str)
        ):
            raise InvalidKeyValue('download_link', download_link)

        source = data.get('source')
        if not (
            source is None
            or source
                and isinstance(source, str)
        ):
            raise InvalidKeyValue('source', source)

        if not data.get('source'):
            source = None
        else:
            try:
                source = DownloadSource(data['source'])
            except ValueError:
                raise InvalidKeyValue('source', data['source'])

        volume_id = data.get('volume_id')
        if not (volume_id and isinstance(volume_id, int)):
            raise InvalidKeyValue('volume_id', volume_id)

        issue_id = data.get('issue_id')
        if not (
            issue_id is None
            or issue_id
                and isinstance(issue_id, int)
        ):
            raise InvalidKeyValue('issue_id', issue_id)

        try:
            reason = BlocklistReason[
                BlocklistReasonID(data.get('reason_id')).name
            ]

        except ValueError:
            raise InvalidKeyValue('reason_id', data.get('reason_id'))

        result = add_to_blocklist(
            web_link=web_link,
            web_title=web_title,
            web_sub_title=web_sub_title,
            download_link=download_link,
            source=source,
            volume_id=volume_id,
            issue_id=issue_id,
            reason=reason
        ).todict()
        return return_api(result, code=201)

    elif request.method == 'DELETE':
        delete_blocklist()
        return return_api({})


@api.route('/blocklist/<int:id>', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_blocklist_entry(id: int):
    if request.method == 'GET':
        result = get_blocklist_entry(id).todict()
        return return_api(result)

    elif request.method == 'DELETE':
        delete_blocklist_entry(id)
        return return_api({})


# =====================
# Credentials
# =====================
@api.route('/credentials', methods=['GET', 'POST'])
@error_handler
@auth
def api_credentials():
    cred = Credentials()

    if request.method == 'GET':
        result = [
            c.todict(hide_password=True)
            for c in cred.get_all()
        ]
        return return_api(result)

    elif request.method == 'POST':
        data = request.get_json()
        if not isinstance(data, dict):
            raise InvalidKeyValue(value=data)

        if 'source' not in data:
            raise KeyNotFound('source')

        try:
            source = CredentialSource(
                data["source"]
            )

        except ValueError:
            raise InvalidKeyValue('source', data["source"])

        result = cred.add(CredentialData(
            id=-1,
            source=source,
            username=data.get("username"),
            email=data.get("email"),
            password=data.get("password"),
            api_key=data.get("api_key")
        ))
        return return_api(result.todict(hide_password=True), code=201)


@api.route('/credentials/<int:id>', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_credential(id: int):
    cred = Credentials()
    if request.method == 'GET':
        result = cred.get_one(id).todict(hide_password=True)
        return return_api(result)

    elif request.method == 'DELETE':
        cred.delete(id)
        return return_api({})

@api.route('/downloadclients/queue', methods=['GET'])
@error_handler
@auth
def api_download_clients_queue():
    result = []
    for client_data in ExternalClients.get_clients():
        if client_data['download_type'] != DownloadType.USENET.value:
            continue
        client = ExternalClients.get_client(client_data['id'])
        if hasattr(client, 'get_queue'):
            result.extend(client.get_queue())
    return return_api(result)


@api.route('/downloadclients/history', methods=['GET'])
@error_handler
@auth
def api_download_clients_history():
    result = []
    for client_data in ExternalClients.get_clients():
        if client_data['download_type'] != DownloadType.USENET.value:
            continue
        client = ExternalClients.get_client(client_data['id'])
        if hasattr(client, 'get_history'):
            result.extend(client.get_history())
    return return_api(result)

# =====================
# Download Clients
# =====================
@api.route('/externalclients', methods=['GET', 'POST'])
@error_handler
@auth
def api_external_clients():
    if request.method == 'GET':
        result = ExternalClients.get_clients()
        for client_data in result:
            if client_data.get('api_token'):
                client_data['api_token'] = Constants.CREDENTIAL_REPLACEMENT
        return return_api(result)

    elif request.method == 'POST':
        data: dict = request.get_json()
        data = {
            k: data.get(k)
            for k in (
                'client_type',
                'title', 'base_url',
                'username', 'password', 'api_token'
            )
        }
        result = ExternalClients.add(**data).get_client_data()
        if result.get('api_token'):
            result['api_token'] = Constants.CREDENTIAL_REPLACEMENT
        return return_api(result, code=201)


@api.route('/externalclients/options', methods=['GET'])
@error_handler
@auth
def api_external_clients_keys():
    result = {
        k: v.required_tokens
        for k, v in ExternalClients.get_client_types().items()
    }
    return return_api(result)


@api.route('/externalclients/test', methods=['POST'])
@error_handler
@auth
def api_external_clients_test():
    data: dict = request.get_json()
    client = None
    client_id = data.get('id')
    if client_id is not None:
        try:
            client_id = int(client_id)
        except (TypeError, ValueError):
            raise InvalidKeyValue('id', client_id)
        client = ExternalClients.get_client(client_id)

    data = {
        k: data.get(k)
        for k in (
            'client_type', 'base_url',
            'username', 'password', 'api_token'
        )
    }

    if client is not None:
        if data['client_type'] is None:
            data['client_type'] = client.client_type
        if data['api_token'] == Constants.CREDENTIAL_REPLACEMENT:
            data['api_token'] = client.api_token

    result = ExternalClients.test(**data)
    return return_api(result)


@api.route('/externalclients/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_external_client(id: int):
    client = ExternalClients.get_client(id)

    if request.method == 'GET':
        result = client.get_client_data()
        if result.get('api_token'):
            result['api_token'] = Constants.CREDENTIAL_REPLACEMENT
        return return_api(result)

    elif request.method == 'PUT':
        data: dict = request.get_json()
        data = {
            k: data.get(k)
            for k in (
                'title', 'base_url',
                'username', 'password', 'api_token'
            )
        }
        client.update_client(data)
        result = client.get_client_data()
        if result.get('api_token'):
            result['api_token'] = Constants.CREDENTIAL_REPLACEMENT
        return return_api(result)

    elif request.method == 'DELETE':
        client.delete_client()
        return return_api({})


# =====================
# Indexers
# =====================
def _mask_indexer_key(indexer_data: Dict[str, Any]) -> Dict[str, Any]:
    if indexer_data.get('api_key'):
        indexer_data['api_key'] = Constants.CREDENTIAL_REPLACEMENT
    return indexer_data


def _provider_indexer_to_legacy(provider: Dict[str, Any]) -> Dict[str, Any]:
    settings = provider.get('settings') or {}
    if not isinstance(settings, dict):
        settings = {}
    implementation = str(provider.get('implementation') or '').lower()
    return _mask_indexer_key({
        'id': provider.get('id'),
        'indexer_type': {
            'newznab': 'Newznab',
            'torznab': 'Torznab',
            'prowlarr': 'Prowlarr'
        }.get(implementation, implementation.title()),
        'title': provider.get('name'),
        'base_url': settings.get('base_url') or settings.get('url') or '',
        'api_key': settings.get('api_key') or '',
        'enabled': provider.get('enabled'),
        'categories': settings.get('categories'),
        'provider_registry': True
    })


def _legacy_indexer_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    indexer_type = str(data.get('indexer_type') or '').lower()
    implementation = {
        'newznab': 'newznab',
        'torznab': 'torznab',
        'prowlarr': 'prowlarr'
    }.get(indexer_type, indexer_type)
    return {
        'name': data.get('title') or data.get('name') or implementation.title(),
        'implementation': implementation,
        'enabled': data.get('enabled', True),
        'priority': data.get('priority') or 25,
        'settings': {
            'base_url': data.get('base_url') or data.get('url') or '',
            'api_key': data.get('api_key') or '',
            'categories': data.get('categories') or ''
        },
        'tags': []
    }


@api.route('/externalindexers', methods=['GET', 'POST'])
@error_handler
@auth
def api_external_indexers():
    if request.method == 'GET':
        provider_indexers = [
            _provider_indexer_to_legacy(provider)
            for provider in get_providers('indexers')
            if str(provider.get('implementation') or '').lower()
            in ('newznab', 'torznab', 'prowlarr')
        ]
        legacy_indexers = [
            _mask_indexer_key(indexer_data)
            for indexer_data in ExternalIndexers.get_indexers()
        ]
        return return_api(provider_indexers + legacy_indexers)

    elif request.method == 'POST':
        data: dict = request.get_json()
        provider = save_provider('indexers', _legacy_indexer_payload(data))
        return return_api(_provider_indexer_to_legacy(provider), code=201)


@api.route('/externalindexers/options', methods=['GET'])
@error_handler
@auth
def api_external_indexer_options():
    return return_api({
        'Newznab': ('title', 'base_url', 'api_key'),
        'Torznab': ('title', 'base_url', 'api_key'),
        'Prowlarr': ('title', 'base_url', 'api_key')
    })


@api.route('/externalindexers/test', methods=['POST'])
@error_handler
@auth
def api_external_indexer_test():
    data: dict = request.get_json()
    indexer_id = data.get('id')
    if indexer_id is not None:
        try:
            indexer_id = int(indexer_id)
        except (TypeError, ValueError):
            raise InvalidKeyValue('id', indexer_id)
        indexer = ExternalIndexers.get_indexer(indexer_id)
        if data.get('indexer_type') is None:
            data['indexer_type'] = indexer.indexer_type
        if data.get('api_key') == Constants.CREDENTIAL_REPLACEMENT:
            data['api_key'] = indexer.api_key

    return return_api(test_provider(
        'indexers',
        _legacy_indexer_payload(data)
    ))


@api.route('/externalindexers/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_external_indexer(id: int):
    try:
        provider = get_provider('indexers', id)
    except InvalidKeyValue:
        provider = None

    if provider is not None:
        if request.method == 'GET':
            return return_api(_provider_indexer_to_legacy(provider))

        elif request.method == 'PUT':
            data = request.get_json()
            payload = _legacy_indexer_payload(data)
            if data.get('api_key') == Constants.CREDENTIAL_REPLACEMENT:
                settings = provider.get('settings') or {}
                if isinstance(settings, dict):
                    payload['settings']['api_key'] = settings.get('api_key')
            return return_api(_provider_indexer_to_legacy(
                save_provider('indexers', payload, id)
            ))

        elif request.method == 'DELETE':
            delete_provider('indexers', id)
            return return_api({})

    indexer = ExternalIndexers.get_indexer(id)

    if request.method == 'GET':
        return return_api(_mask_indexer_key(indexer.get_indexer_data()))

    elif request.method == 'PUT':
        data: dict = request.get_json()
        data = {
            k: data.get(k)
            for k in (
                'title', 'base_url',
                'api_key', 'enabled', 'categories'
            )
        }
        indexer.update_indexer(data)
        return return_api(_mask_indexer_key(indexer.get_indexer_data()))

    elif request.method == 'DELETE':
        indexer.delete_indexer()
        return return_api({})


# =====================
# Mass Editor
# =====================
@api.route('/masseditor', methods=['POST'])
@error_handler
@auth
def api_mass_editor():
    data = request.get_json()
    if not isinstance(data, dict):
        raise InvalidKeyValue('body', data)
    if 'action' not in data:
        raise KeyNotFound('action')
    if 'volume_ids' not in data:
        raise KeyNotFound('volume_ids')

    action: str = data['action']
    volume_ids: Union[List[int], Any] = data['volume_ids']
    args: Dict[str, Any] = data.get('args', {})

    if not (
        isinstance(volume_ids, list)
        and all(isinstance(v, int) for v in volume_ids)
    ):
        raise InvalidKeyValue('volume_ids', volume_ids)

    if not isinstance(args, dict):
        raise InvalidKeyValue('args', args)

    run_mass_editor_action(action, volume_ids, **args)
    return return_api({})


# =====================
# Files
# =====================
@api.route('/files/<int:f_id>', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_files(f_id: int):
    if request.method == 'GET':
        result = FilesDB.fetch(file_id=f_id)[0]
        return return_api(result)

    elif request.method == 'DELETE':
        delete_issue_file(f_id)
        return return_api({})
