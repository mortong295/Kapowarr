# -*- coding: utf-8 -*-

"""*arr-style feature foundations for profiles, indexers and planning.

The implementation intentionally keeps these features data-backed and usable
without pulling search/download behavior into this module. Search providers,
metadata writers and notification senders can build on these tables over time.
"""

from __future__ import annotations

from csv import DictReader
from io import StringIO
from json import dumps, loads
from os.path import join
from time import gmtime, strftime, time
from typing import Any, Dict, Iterable, List, Mapping, Tuple, Union
from xml.etree.ElementTree import Element, ParseError, SubElement, fromstring, tostring

from requests import RequestException

from backend.base.custom_exceptions import InvalidKeyValue, KeyNotFound
from backend.base.files import create_folder
from backend.base.helpers import Session
from backend.implementations.volumes import Library
from backend.internals.db import get_db

JSONDict = Dict[str, Any]


def _now() -> int:
    return round(time())


def _to_json(data: Union[Mapping[str, Any], List[Any], None]) -> str:
    return dumps(data or {}, separators=(',', ':'))


def _from_json(data: Union[str, bytes, None], default: Any) -> Any:
    if not data:
        return default
    if isinstance(data, bytes):
        data = data.decode()
    return loads(data)


def _row_to_dict(row: Dict[str, Any], json_fields: Iterable[str]) -> Dict[str, Any]:
    result = dict(row)
    for field in json_fields:
        result[field] = _from_json(result.get(field), {})
    return result


def _require_dict(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise InvalidKeyValue('body', data)
    return data


def _require_name(data: Mapping[str, Any]) -> str:
    name = data.get('name')
    if not isinstance(name, str) or not name.strip():
        raise KeyNotFound('name')
    return name.strip()


def _get_row(table: str, id: int) -> Dict[str, Any]:
    row = get_db().execute(
        f"SELECT * FROM {table} WHERE id = ? LIMIT 1;",
        (id,)
    ).fetchonedict()
    if row is None:
        raise InvalidKeyValue('id', id)
    return row


def _parse_priority(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise InvalidKeyValue('priority', value)

# region Profiles
DEFAULT_QUALITY_PROFILE = {
    'name': 'Any Comic',
    'upgrade_allowed': True,
    'cutoff': 'cbz',
    'allowed_formats': ['cbz', 'cbr', 'pdf', 'epub'],
    'preferred_formats': ['cbz', 'cbr'],
    'custom_formats': {
        'digital': 100,
        'tagged': 25,
        'scan': -10
    }
}

DEFAULT_METADATA_PROFILE = {
    'write_comicinfo': True,
    'write_series_json': True,
    'embed_comicinfo': False,
    'preserve_existing': True
}


def ensure_default_profile() -> int:
    cursor = get_db()
    profile_id = cursor.execute(
        "SELECT id FROM arr_quality_profiles ORDER BY id LIMIT 1;"
    ).exists()
    if profile_id:
        return profile_id

    created_at = _now()
    cursor.execute(
        """
        INSERT INTO arr_quality_profiles(
            name, upgrade_allowed, cutoff,
            allowed_formats, preferred_formats,
            custom_formats, metadata_profile,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?);
        """,
        (
            DEFAULT_QUALITY_PROFILE['name'],
            DEFAULT_QUALITY_PROFILE['upgrade_allowed'],
            DEFAULT_QUALITY_PROFILE['cutoff'],
            _to_json(DEFAULT_QUALITY_PROFILE['allowed_formats']),
            _to_json(DEFAULT_QUALITY_PROFILE['preferred_formats']),
            _to_json(DEFAULT_QUALITY_PROFILE['custom_formats']),
            _to_json(DEFAULT_METADATA_PROFILE),
            created_at,
            created_at
        )
    )
    return cursor.lastrowid


def get_default_profile_id() -> int:
    configured_id = 0
    try:
        from backend.internals.settings import Settings
        configured_id = Settings().sv.default_quality_profile_id
    except Exception:
        configured_id = 0

    if configured_id and profile_exists(configured_id):
        return configured_id

    return ensure_default_profile()


def profile_exists(id: int) -> bool:
    ensure_default_profile()
    return get_db().execute(
        "SELECT 1 FROM arr_quality_profiles WHERE id = ? LIMIT 1;",
        (id,)
    ).fetchone() is not None


def get_profiles() -> List[Dict[str, Any]]:
    ensure_default_profile()
    rows = get_db().execute(
        "SELECT * FROM arr_quality_profiles ORDER BY name;"
    ).fetchalldict()
    return [
        _row_to_dict(
            r,
            ('allowed_formats', 'preferred_formats', 'custom_formats',
             'metadata_profile')
        )
        for r in rows
    ]


def get_profile(id: int) -> Dict[str, Any]:
    ensure_default_profile()
    return _row_to_dict(
        _get_row('arr_quality_profiles', id),
        ('allowed_formats', 'preferred_formats', 'custom_formats',
         'metadata_profile')
    )


def save_profile(data: Any, id: Union[int, None] = None) -> Dict[str, Any]:
    payload = _require_dict(data)
    name = _require_name(payload)
    now = _now()
    allowed_formats = payload.get('allowed_formats', ['cbz', 'cbr'])
    preferred_formats = payload.get('preferred_formats', ['cbz'])
    custom_formats = payload.get('custom_formats', {})
    metadata_profile = payload.get('metadata_profile', DEFAULT_METADATA_PROFILE)

    if not isinstance(allowed_formats, list):
        raise InvalidKeyValue('allowed_formats', allowed_formats)
    if not isinstance(preferred_formats, list):
        raise InvalidKeyValue('preferred_formats', preferred_formats)
    if not isinstance(custom_formats, dict):
        raise InvalidKeyValue('custom_formats', custom_formats)
    if not isinstance(metadata_profile, dict):
        raise InvalidKeyValue('metadata_profile', metadata_profile)

    values = {
        'name': name,
        'upgrade_allowed': bool(payload.get('upgrade_allowed', True)),
        'cutoff': payload.get('cutoff') or '',
        'allowed_formats': _to_json(allowed_formats),
        'preferred_formats': _to_json(preferred_formats),
        'custom_formats': _to_json(custom_formats),
        'metadata_profile': _to_json(metadata_profile),
        'updated_at': now
    }

    cursor = get_db()
    if id is None:
        cursor.execute(
            """
            INSERT INTO arr_quality_profiles(
                name, upgrade_allowed, cutoff,
                allowed_formats, preferred_formats,
                custom_formats, metadata_profile,
                created_at, updated_at
            ) VALUES (
                :name, :upgrade_allowed, :cutoff,
                :allowed_formats, :preferred_formats,
                :custom_formats, :metadata_profile,
                :created_at, :updated_at
            );
            """,
            {**values, 'created_at': now}
        )
        id = cursor.lastrowid
    else:
        _get_row('arr_quality_profiles', id)
        cursor.execute(
            """
            UPDATE arr_quality_profiles
            SET
                name = :name,
                upgrade_allowed = :upgrade_allowed,
                cutoff = :cutoff,
                allowed_formats = :allowed_formats,
                preferred_formats = :preferred_formats,
                custom_formats = :custom_formats,
                metadata_profile = :metadata_profile,
                updated_at = :updated_at
            WHERE id = :id;
            """,
            {**values, 'id': id}
        )

    return get_profile(id)


def delete_profile(id: int) -> None:
    _get_row('arr_quality_profiles', id)
    get_db().execute("DELETE FROM arr_quality_profiles WHERE id = ?;", (id,))
    return


def _score_library_file(
    filepath: str,
    profile: Mapping[str, Any]
) -> Dict[str, Any]:
    from backend.features.search import _score_quality_profile

    return _score_quality_profile({
        'display_title': filepath,
        'link': filepath,
        'source': 'library'
    }, profile)


def _cutoff_score(profile: Mapping[str, Any]) -> int:
    cutoff = str(profile.get('cutoff') or '').strip().lower()
    if not cutoff:
        return 0
    return int(
        _score_library_file(f'cutoff.{cutoff}', profile)['quality_score']
    )


def get_cutoff_unmet_issues(
    limit: int = 200,
    quality_profile_id: Union[int, None] = None
) -> List[Dict[str, Any]]:
    """Return downloaded monitored issues below their profile cutoff."""
    ensure_default_profile()
    profile_filter = ''
    params: List[Any] = []
    if quality_profile_id is not None:
        profile_filter = 'AND v.quality_profile_id = ?'
        params.append(quality_profile_id)

    rows = get_db().execute(f"""
        SELECT
            i.id AS issue_id,
            i.issue_number,
            i.title AS issue_title,
            i.date,
            v.id AS volume_id,
            v.title AS volume_title,
            v.year,
            v.publisher,
            v.volume_number,
            v.quality_profile_id,
            aqp.name AS quality_profile_name,
            f.id AS file_id,
            f.filepath
        FROM issues i
        INNER JOIN volumes v
            ON i.volume_id = v.id
        INNER JOIN issues_files if
            ON i.id = if.issue_id
        INNER JOIN files f
            ON if.file_id = f.id
        LEFT JOIN arr_quality_profiles aqp
            ON v.quality_profile_id = aqp.id
        WHERE
            v.monitored = 1
            AND i.monitored = 1
            {profile_filter}
        ORDER BY v.title, i.calculated_issue_number, f.filepath;
        """, tuple(params)).fetchalldict()

    profile_cache: Dict[int, Dict[str, Any]] = {}
    cutoff_cache: Dict[int, int] = {}
    issues: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        profile_id = row['quality_profile_id'] or get_default_profile_id()
        if profile_id not in profile_cache:
            profile_cache[profile_id] = get_profile(profile_id)
            cutoff_cache[profile_id] = _cutoff_score(profile_cache[profile_id])

        profile = profile_cache[profile_id]
        cutoff = str(profile.get('cutoff') or '').strip().lower()
        if not profile.get('upgrade_allowed') or not cutoff:
            continue

        quality = _score_library_file(row['filepath'], profile)
        current_score = int(quality.get('quality_score') or 0)
        current = issues.get(row['issue_id'])
        if current and current['quality_score'] >= current_score:
            continue

        issues[row['issue_id']] = {
            'issue_id': row['issue_id'],
            'issue_number': row['issue_number'],
            'issue_title': row['issue_title'],
            'date': row['date'],
            'volume_id': row['volume_id'],
            'volume_title': row['volume_title'],
            'year': row['year'],
            'publisher': row['publisher'],
            'volume_number': row['volume_number'],
            'quality_profile_id': profile_id,
            'quality_profile_name': (
                row['quality_profile_name'] or profile.get('name')
            ),
            'cutoff': cutoff,
            'cutoff_score': cutoff_cache[profile_id],
            'file_id': row['file_id'],
            'filepath': row['filepath'],
            **quality
        }

    unmet = [
        issue
        for issue in issues.values()
        if (
            not issue.get('quality_profile_match', True)
            or issue.get('quality_format') == 'unknown'
            or int(issue.get('quality_score') or 0)
            < int(issue.get('cutoff_score') or 0)
        )
    ]
    unmet.sort(key=lambda i: (
        i['volume_title'],
        str(i['issue_number']),
        -int(i.get('cutoff_score') or 0) + int(i.get('quality_score') or 0)
    ))
    return unmet[:limit]


# region Provider-backed settings
PROVIDER_TABLES = {
    'indexers': 'arr_indexers',
    'connections': 'arr_connections',
    'importlists': 'arr_import_lists'
}

PROVIDER_JSON_FIELDS = {
    'indexers': ('settings', 'tags'),
    'connections': ('settings', 'tags', 'events'),
    'importlists': ('settings', 'tags')
}

DEFAULT_PROVIDERS = {
    'indexers': [
        {
            'name': 'GetComics',
            'implementation': 'getcomics',
            'enabled': True,
            'priority': 25,
            'settings': {'source': 'GetComics'},
            'tags': []
        }
    ],
    'connections': [],
    'importlists': []
}


def ensure_default_providers(feature: str) -> None:
    table = PROVIDER_TABLES[feature]
    cursor = get_db()
    if cursor.execute(f"SELECT 1 FROM {table} LIMIT 1;").fetchone():
        return

    for provider in DEFAULT_PROVIDERS[feature]:
        save_provider(feature, provider)
    return


def _provider_to_dict(feature: str, row: Dict[str, Any]) -> Dict[str, Any]:
    result = _row_to_dict(row, PROVIDER_JSON_FIELDS[feature])
    result['status'] = 'available' if result.get('enabled') else 'disabled'
    return result


def get_providers(feature: str) -> List[Dict[str, Any]]:
    ensure_default_providers(feature)
    table = PROVIDER_TABLES[feature]
    rows = get_db().execute(
        f"SELECT * FROM {table} ORDER BY priority, name;"
    ).fetchalldict()
    return [_provider_to_dict(feature, r) for r in rows]


def get_provider(feature: str, id: int) -> Dict[str, Any]:
    ensure_default_providers(feature)
    return _provider_to_dict(feature, _get_row(PROVIDER_TABLES[feature], id))


def save_provider(
    feature: str,
    data: Any,
    id: Union[int, None] = None
) -> Dict[str, Any]:
    payload = _require_dict(data)
    name = _require_name(payload)
    now = _now()
    table = PROVIDER_TABLES[feature]

    settings = payload.get('settings', {})
    tags = payload.get('tags', [])
    if not isinstance(settings, dict):
        raise InvalidKeyValue('settings', settings)
    if not isinstance(tags, list):
        raise InvalidKeyValue('tags', tags)

    implementation = payload.get('implementation') or payload.get('type')
    if not isinstance(implementation, str) or not implementation.strip():
        raise KeyNotFound('implementation')

    values = {
        'name': name,
        'implementation': implementation.strip(),
        'enabled': bool(payload.get('enabled', True)),
        'priority': _parse_priority(payload.get('priority', 25)),
        'settings': _to_json(settings),
        'tags': _to_json(tags),
        'updated_at': now
    }

    if feature == 'connections':
        events = payload.get('events', [])
        if not isinstance(events, list):
            raise InvalidKeyValue('events', events)
        values['events'] = _to_json(events)

    cursor = get_db()
    if id is None:
        if feature == 'connections':
            cursor.execute(
                f"""
                INSERT INTO {table}(
                    name, implementation, enabled, priority,
                    settings, tags, events, created_at, updated_at
                ) VALUES (
                    :name, :implementation, :enabled, :priority,
                    :settings, :tags, :events, :created_at, :updated_at
                );
                """,
                {**values, 'created_at': now}
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO {table}(
                    name, implementation, enabled, priority,
                    settings, tags, created_at, updated_at
                ) VALUES (
                    :name, :implementation, :enabled, :priority,
                    :settings, :tags, :created_at, :updated_at
                );
                """,
                {**values, 'created_at': now}
            )
        id = cursor.lastrowid
    else:
        _get_row(table, id)
        if feature == 'connections':
            cursor.execute(
                f"""
                UPDATE {table}
                SET
                    name = :name,
                    implementation = :implementation,
                    enabled = :enabled,
                    priority = :priority,
                    settings = :settings,
                    tags = :tags,
                    events = :events,
                    updated_at = :updated_at
                WHERE id = :id;
                """,
                {**values, 'id': id}
            )
        else:
            cursor.execute(
                f"""
                UPDATE {table}
                SET
                    name = :name,
                    implementation = :implementation,
                    enabled = :enabled,
                    priority = :priority,
                    settings = :settings,
                    tags = :tags,
                    updated_at = :updated_at
                WHERE id = :id;
                """,
                {**values, 'id': id}
            )

    return get_provider(feature, id)


def delete_provider(feature: str, id: int) -> None:
    table = PROVIDER_TABLES[feature]
    _get_row(table, id)
    get_db().execute(f"DELETE FROM {table} WHERE id = ?;", (id,))
    return


def test_provider(feature: str, data: Mapping[str, Any]) -> Dict[str, Any]:
    implementation = data.get('implementation') or data.get('type')
    if not implementation:
        raise KeyNotFound('implementation')

    supported = {
        'indexers': {
            'getcomics', 'newznab', 'torznab', 'rawrss'
        },
        'connections': {
            'webhook', 'discord', 'gotify', 'plex', 'jellyfin'
        },
        'importlists': {
            'comicvine', 'pulllist', 'mylar', 'csv', 'json'
        }
    }
    implementation = str(implementation).lower()
    is_supported = implementation in supported[feature]

    if feature == 'connections' and is_supported:
        payload = {
            'event': 'test',
            'title': 'Kapowarr test notification',
            'message': 'Connection settings were validated by Kapowarr.'
        }
        settings = data.get('settings') or {}
        if isinstance(settings, dict) and settings.get('send_test'):
            result = _send_connection(
                {'name': data.get('name') or implementation,
                 'implementation': implementation,
                 'settings': settings},
                payload
            )
            return {
                'status': 'ok' if result['success'] else 'failed',
                'implementation': implementation,
                'message': result['message']
            }

    return {
        'status': 'ok' if is_supported else 'unsupported',
        'implementation': implementation,
        'message': (
            'Provider type is recognised and can be saved.'
            if is_supported else
            'Provider type is not recognised by the V1 provider registry.'
        )
    }


# region Connections
CONNECTION_EVENT_LABELS = {
    'test': 'Test',
    'download_grabbed': 'Download grabbed',
    'download_imported': 'Download imported',
    'download_failed': 'Download failed',
    'import_list_synced': 'Import list synced'
}


def _connection_settings(connection: Mapping[str, Any]) -> Mapping[str, Any]:
    settings = connection.get('settings') or {}
    return settings if isinstance(settings, dict) else {}


def _connection_events(connection: Mapping[str, Any]) -> List[str]:
    events = connection.get('events') or []
    if not isinstance(events, list):
        return []
    return [str(event) for event in events]


def _connection_accepts_event(
    connection: Mapping[str, Any],
    event: str
) -> bool:
    events = _connection_events(connection)
    return not events or event in events


def _post_connection_payload(
    url: str,
    payload: Union[Mapping[str, Any], None] = None,
    headers: Union[Mapping[str, str], None] = None,
    params: Union[Mapping[str, str], None] = None
) -> Dict[str, Any]:
    try:
        with Session() as session:
            response = session.post(
                url,
                json=payload,
                headers=dict(headers or {}),
                params=dict(params or {})
            )
            response.raise_for_status()
            return {
                'success': True,
                'status_code': response.status_code,
                'message': 'Notification sent.'
            }
    except RequestException as exc:
        return {
            'success': False,
            'status_code': None,
            'message': str(exc) or 'Notification failed.'
        }


def _send_webhook_connection(
    connection: Mapping[str, Any],
    payload: Mapping[str, Any]
) -> Dict[str, Any]:
    settings = _connection_settings(connection)
    url = settings.get('url') or settings.get('webhook_url')
    if not isinstance(url, str) or not url.strip():
        return {'success': False, 'message': 'Missing webhook URL.'}

    headers = settings.get('headers') if isinstance(settings.get('headers'), dict) else {}
    return _post_connection_payload(url.strip(), payload, headers)


def _send_discord_connection(
    connection: Mapping[str, Any],
    payload: Mapping[str, Any]
) -> Dict[str, Any]:
    settings = _connection_settings(connection)
    url = settings.get('webhook_url') or settings.get('url')
    if not isinstance(url, str) or not url.strip():
        return {'success': False, 'message': 'Missing Discord webhook URL.'}

    discord_payload = {
        'content': payload.get('message') or payload.get('title'),
        'embeds': [{
            'title': payload.get('title') or CONNECTION_EVENT_LABELS.get(
                str(payload.get('event')), 'Kapowarr'
            ),
            'description': payload.get('message') or '',
            'fields': [
                {'name': key, 'value': str(value), 'inline': True}
                for key, value in payload.items()
                if key not in ('title', 'message') and value is not None
            ][:12]
        }]
    }
    return _post_connection_payload(url.strip(), discord_payload)


def _send_gotify_connection(
    connection: Mapping[str, Any],
    payload: Mapping[str, Any]
) -> Dict[str, Any]:
    settings = _connection_settings(connection)
    base_url = settings.get('base_url') or settings.get('url')
    token = settings.get('token')
    if not isinstance(base_url, str) or not base_url.strip():
        return {'success': False, 'message': 'Missing Gotify URL.'}
    if not isinstance(token, str) or not token.strip():
        return {'success': False, 'message': 'Missing Gotify token.'}

    gotify_payload = {
        'title': payload.get('title') or 'Kapowarr',
        'message': payload.get('message') or '',
        'priority': int(settings.get('priority') or 5)
    }
    return _post_connection_payload(
        base_url.rstrip('/') + '/message',
        gotify_payload,
        {'Authorization': f'Bearer {token.strip()}'}
    )


def _send_plex_connection(
    connection: Mapping[str, Any],
    payload: Mapping[str, Any]
) -> Dict[str, Any]:
    settings = _connection_settings(connection)
    base_url = settings.get('base_url') or settings.get('url')
    token = (
        settings.get('token')
        or settings.get('api_key')
        or settings.get('plex_token')
    )
    section_id = (
        settings.get('section_id')
        or settings.get('library_section_id')
        or settings.get('section_key')
        or 'all'
    )
    if not isinstance(base_url, str) or not base_url.strip():
        return {'success': False, 'message': 'Missing Plex URL.'}
    if not isinstance(token, str) or not token.strip():
        return {'success': False, 'message': 'Missing Plex token.'}

    params = {'X-Plex-Token': token.strip()}
    path = settings.get('path')
    if isinstance(path, str) and path.strip():
        params['path'] = path.strip()

    return _post_connection_payload(
        (
            base_url.rstrip('/')
            + f'/library/sections/{str(section_id).strip()}/refresh'
        ),
        None,
        params=params
    )


def _send_jellyfin_connection(
    connection: Mapping[str, Any],
    payload: Mapping[str, Any]
) -> Dict[str, Any]:
    settings = _connection_settings(connection)
    base_url = settings.get('base_url') or settings.get('url')
    token = (
        settings.get('token')
        or settings.get('api_key')
        or settings.get('jellyfin_api_key')
    )
    item_id = settings.get('item_id') or settings.get('library_id')
    if not isinstance(base_url, str) or not base_url.strip():
        return {'success': False, 'message': 'Missing Jellyfin URL.'}
    if not isinstance(token, str) or not token.strip():
        return {'success': False, 'message': 'Missing Jellyfin API key.'}

    endpoint = (
        f"/Items/{str(item_id).strip()}/Refresh"
        if item_id else
        '/Library/Refresh'
    )
    return _post_connection_payload(
        base_url.rstrip('/') + endpoint,
        None,
        {'X-Emby-Token': token.strip()}
    )


def _send_connection(
    connection: Mapping[str, Any],
    payload: Mapping[str, Any]
) -> Dict[str, Any]:
    implementation = str(connection.get('implementation') or '').lower()
    if implementation == 'webhook':
        return _send_webhook_connection(connection, payload)
    if implementation == 'discord':
        return _send_discord_connection(connection, payload)
    if implementation == 'gotify':
        return _send_gotify_connection(connection, payload)
    if implementation == 'plex':
        return _send_plex_connection(connection, payload)
    if implementation == 'jellyfin':
        return _send_jellyfin_connection(connection, payload)
    return {
        'success': False,
        'message': f'{implementation or "connection"} dispatch is not implemented.'
    }


def send_connection_event(
    event: str,
    payload: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    full_payload = {
        'event': event,
        'event_label': CONNECTION_EVENT_LABELS.get(event, event),
        **payload
    }
    results: List[Dict[str, Any]] = []
    for connection in get_providers('connections'):
        if not connection.get('enabled'):
            continue
        if not _connection_accepts_event(connection, event):
            continue
        result = _send_connection(connection, full_payload)
        results.append({
            'id': connection.get('id'),
            'name': connection.get('name'),
            'implementation': connection.get('implementation'),
            **result
        })
    return results


# region Pull lists

def _match_pull_list_item(item: Mapping[str, Any]) -> Tuple[Union[int, None], Union[int, None], int]:
    series = str(item.get('series') or '').strip().lower()
    issue_number = str(item.get('issue_number') or '').strip()
    if not series:
        return None, None, 0

    volume_row = get_db().execute(
        """
        SELECT id FROM volumes
        WHERE LOWER(title) = ? OR LOWER(alt_title) = ?
        ORDER BY year DESC
        LIMIT 1;
        """,
        (series, series)
    ).fetchone()
    if volume_row is None:
        return None, None, 0

    issue_row = None
    if issue_number:
        issue_row = get_db().execute(
            """
            SELECT id FROM issues
            WHERE volume_id = ? AND issue_number = ?
            LIMIT 1;
            """,
            (volume_row['id'], issue_number)
        ).fetchone()

    return (
        volume_row['id'],
        issue_row['id'] if issue_row else None,
        100 if issue_row else 75
    )


def get_pull_list() -> List[Dict[str, Any]]:
    return get_db().execute(
        "SELECT * FROM pull_list_items ORDER BY release_date, publisher, series;"
    ).fetchalldict()


def get_calendar_pull_list(days: int = 90) -> List[Dict[str, Any]]:
    start = strftime('%Y-%m-%d', gmtime(_now()))
    end = strftime('%Y-%m-%d', gmtime(_now() + days * 86400))
    return get_db().execute(
        """
        SELECT * FROM pull_list_items
        WHERE
            release_date = ''
            OR release_date IS NULL
            OR (release_date >= ? AND release_date <= ?)
        ORDER BY
            CASE WHEN release_date IS NULL OR release_date = '' THEN 1 ELSE 0 END,
            release_date,
            publisher,
            series,
            issue_number;
        """,
        (start, end)
    ).fetchalldict()


def get_searchable_pull_list_items() -> List[Dict[str, Any]]:
    """Return matched pull-list items that can be searched/grabbed."""
    return get_db().execute(
        """
        SELECT
            pli.*,
            v.title AS volume_title,
            i.issue_number AS matched_issue_number,
            COUNT(if.file_id) AS downloaded_files
        FROM pull_list_items pli
        INNER JOIN volumes v
            ON pli.volume_id = v.id
        LEFT JOIN issues i
            ON pli.issue_id = i.id
        LEFT JOIN issues_files if
            ON pli.issue_id = if.issue_id
        WHERE
            pli.status IN ('pending', 'wanted')
            AND v.monitored = 1
            AND (i.id IS NULL OR i.monitored = 1)
        GROUP BY pli.id
        HAVING downloaded_files = 0
        ORDER BY pli.release_date, pli.publisher, pli.series, pli.issue_number;
        """
    ).fetchalldict()


def update_pull_list_item_status(id: int, status: str) -> Dict[str, Any]:
    if not isinstance(status, str) or not status.strip():
        raise InvalidKeyValue('status', status)
    now = _now()
    cursor = get_db()
    cursor.execute(
        """
        UPDATE pull_list_items
        SET status = ?, updated_at = ?
        WHERE id = ?;
        """,
        (status.strip(), now, id)
    )
    row = cursor.execute(
        "SELECT * FROM pull_list_items WHERE id = ? LIMIT 1;",
        (id,)
    ).fetchonedict()
    if row is None:
        raise InvalidKeyValue('id', id)
    return row


def delete_pull_list_item(id: int) -> None:
    cursor = get_db()
    row = cursor.execute(
        "SELECT id FROM pull_list_items WHERE id = ? LIMIT 1;",
        (id,)
    ).fetchonedict()
    if row is None:
        raise InvalidKeyValue('id', id)
    cursor.execute("DELETE FROM pull_list_items WHERE id = ?;", (id,))
    return


def save_pull_list_item(data: Any) -> Dict[str, Any]:
    payload = _require_dict(data)
    series = payload.get('series')
    if not isinstance(series, str) or not series.strip():
        raise KeyNotFound('series')

    volume_id, issue_id, confidence = _match_pull_list_item(payload)
    now = _now()
    cursor = get_db()
    cursor.execute(
        """
        INSERT INTO pull_list_items(
            provider, release_date, publisher, series, issue_number,
            title, volume_id, issue_id, match_confidence,
            status, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?);
        """,
        (
            payload.get('provider') or 'manual',
            payload.get('release_date') or '',
            payload.get('publisher') or '',
            series.strip(),
            payload.get('issue_number') or '',
            payload.get('title') or '',
            volume_id,
            issue_id,
            confidence,
            payload.get('status') or 'pending',
            now,
            now
        )
    )
    return get_db().execute(
        "SELECT * FROM pull_list_items WHERE id = ? LIMIT 1;",
        (cursor.lastrowid,)
    ).fetchonedict() or {}


def _normalise_import_list_items(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        raise InvalidKeyValue('items', items)

    normalised: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise InvalidKeyValue('items', items)
        normalised.append({
            'provider': item.get('provider'),
            'release_date': (
                item.get('release_date')
                or item.get('date')
                or item.get('onsale_date')
                or ''
            ),
            'publisher': item.get('publisher') or '',
            'series': item.get('series') or item.get('title') or '',
            'issue_number': (
                item.get('issue_number')
                or item.get('issue')
                or item.get('number')
                or ''
            ),
            'title': item.get('issue_title') or item.get('subtitle') or '',
            'status': item.get('status') or 'pending'
        })

    return normalised


def _pull_items_from_rss(feed_body: str) -> List[Dict[str, Any]]:
    if not feed_body:
        return []

    try:
        root = fromstring(feed_body)
    except ParseError:
        return []

    items: List[Dict[str, Any]] = []
    for item in root.findall('.//item'):
        title = item.findtext('title') or ''
        description = item.findtext('description') or ''
        pub_date = item.findtext('pubDate') or item.findtext('date') or ''
        if not title.strip():
            continue
        items.append({
            'release_date': pub_date.strip(),
            'publisher': '',
            'series': title.strip(),
            'issue_number': '',
            'title': description.strip(),
            'status': 'pending'
        })

    for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
        title = entry.findtext('{http://www.w3.org/2005/Atom}title') or ''
        updated = entry.findtext('{http://www.w3.org/2005/Atom}updated') or ''
        summary = entry.findtext('{http://www.w3.org/2005/Atom}summary') or ''
        if not title.strip():
            continue
        items.append({
            'release_date': updated.strip(),
            'publisher': '',
            'series': title.strip(),
            'issue_number': '',
            'title': summary.strip(),
            'status': 'pending'
        })

    return items


def _pull_items_from_csv(csv_body: str) -> List[Dict[str, Any]]:
    rows = list(DictReader(StringIO(csv_body or '')))
    return _normalise_import_list_items(rows)


def _pull_items_from_json(json_body: str) -> List[Dict[str, Any]]:
    parsed = loads(json_body or '[]')
    if isinstance(parsed, dict):
        parsed = parsed.get('items') or parsed.get('pull_list') or []
    return _normalise_import_list_items(parsed)


def _fetch_import_list_body(url: Any) -> str:
    if not isinstance(url, str) or not url.strip():
        return ''

    try:
        with Session() as session:
            response = session.get(url.strip())
            response.raise_for_status()
            return response.text
    except RequestException:
        return ''


def _load_import_list_items(provider: Mapping[str, Any]) -> List[Dict[str, Any]]:
    implementation = str(provider.get('implementation') or '').lower()
    settings = provider.get('settings') or {}
    if not isinstance(settings, dict):
        settings = {}

    if isinstance(settings.get('items'), list):
        return _normalise_import_list_items(settings['items'])

    body = settings.get('body')
    if not isinstance(body, str):
        body = _fetch_import_list_body(
            settings.get('url') or settings.get('feed_url')
        )

    if implementation in ('json', 'mylar'):
        return _pull_items_from_json(body)
    if implementation == 'csv':
        return _pull_items_from_csv(body)
    if implementation == 'pulllist':
        content_type = str(settings.get('format') or '').lower()
        if content_type == 'json':
            return _pull_items_from_json(body)
        if content_type == 'csv':
            return _pull_items_from_csv(body)
        return _pull_items_from_rss(body)

    return []


def sync_import_list(id: int, notify: bool = True) -> Dict[str, Any]:
    provider = get_provider('importlists', id)
    provider_name = provider['name']
    now = _now()
    items = _load_import_list_items(provider)
    cursor = get_db()
    cursor.execute(
        "DELETE FROM pull_list_items WHERE provider = ?;",
        (provider_name,)
    )

    synced = 0
    for item in items:
        item = {**item, 'provider': provider_name}
        if not str(item.get('series') or '').strip():
            continue
        save_pull_list_item(item)
        synced += 1

    cursor.execute(
        "UPDATE arr_import_lists SET last_sync = ?, updated_at = ? WHERE id = ?;",
        (now, now, id)
    )
    message = f'Synced {synced} pull-list item(s).'
    if notify:
        send_connection_event('import_list_synced', {
            'title': 'Import list synced',
            'message': message,
            'provider': provider_name,
            'items_synced': synced
        })
    return {
        'id': id,
        'name': provider_name,
        'status': 'synced',
        'last_sync': now,
        'items_synced': synced,
        'message': message
    }


def sync_enabled_import_lists(notify: bool = True) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for provider in get_providers('importlists'):
        if not provider.get('enabled'):
            continue
        results.append(sync_import_list(provider['id'], notify=notify))
    return results


# region Story arcs

def _match_story_arc_issue(issue: Mapping[str, Any]) -> Dict[str, Any]:
    if issue.get('volume_id') and issue.get('issue_id'):
        return dict(issue)

    series = str(
        issue.get('series')
        or issue.get('volume_title')
        or issue.get('volume')
        or ''
    ).strip().lower()
    issue_number = str(
        issue.get('issue_number')
        or issue.get('number')
        or ''
    ).strip()

    result = dict(issue)
    if not series:
        return result

    volume = get_db().execute(
        """
        SELECT id, title FROM volumes
        WHERE LOWER(title) = ? OR LOWER(alt_title) = ?
        ORDER BY year DESC
        LIMIT 1;
        """,
        (series, series)
    ).fetchonedict()
    if volume is None:
        return result

    result.setdefault('volume_id', volume['id'])
    if not result.get('title'):
        result['title'] = issue.get('issue_title') or ''

    if issue_number and not result.get('issue_id'):
        matched_issue = get_db().execute(
            """
            SELECT id, title FROM issues
            WHERE volume_id = ? AND issue_number = ?
            LIMIT 1;
            """,
            (volume['id'], issue_number)
        ).fetchonedict()
        if matched_issue:
            result['issue_id'] = matched_issue['id']
            if not result.get('title'):
                result['title'] = matched_issue.get('title') or ''

    return result


def get_story_arcs() -> List[Dict[str, Any]]:
    arcs = get_db().execute(
        "SELECT * FROM story_arcs ORDER BY title;"
    ).fetchalldict()
    for arc in arcs:
        arc['issues'] = get_story_arc_issues(arc['id'])
    return arcs


def get_story_arc(id: int) -> Dict[str, Any]:
    arc = _get_row('story_arcs', id)
    arc['issues'] = get_story_arc_issues(id)
    return arc


def save_story_arc(data: Any, id: Union[int, None] = None) -> Dict[str, Any]:
    payload = _require_dict(data)
    title = _require_name({'name': payload.get('title') or payload.get('name')})
    now = _now()
    cursor = get_db()
    values = {
        'title': title,
        'description': payload.get('description') or '',
        'comicvine_id': payload.get('comicvine_id'),
        'monitored': bool(payload.get('monitored', True)),
        'updated_at': now
    }
    if id is None:
        cursor.execute(
            """
            INSERT INTO story_arcs(
                title, description, comicvine_id, monitored, created_at, updated_at
            ) VALUES (:title, :description, :comicvine_id, :monitored,
                :created_at, :updated_at);
            """,
            {**values, 'created_at': now}
        )
        id = cursor.lastrowid
    else:
        _get_row('story_arcs', id)
        cursor.execute(
            """
            UPDATE story_arcs
            SET title = :title,
                description = :description,
                comicvine_id = :comicvine_id,
                monitored = :monitored,
                updated_at = :updated_at
            WHERE id = :id;
            """,
            {**values, 'id': id}
        )

    if isinstance(payload.get('issues'), list):
        replace_story_arc_issues(id, payload['issues'])

    return get_story_arc(id)


def delete_story_arc(id: int) -> None:
    _get_row('story_arcs', id)
    get_db().execute("DELETE FROM story_arcs WHERE id = ?;", (id,))
    return


def get_story_arc_issues(story_arc_id: int) -> List[Dict[str, Any]]:
    return get_db().execute(
        """
        SELECT
            sai.*,
            v.title AS volume_title,
            i.issue_number AS matched_issue_number,
            COUNT(if.file_id) > 0 AS downloaded
        FROM story_arc_issues sai
        LEFT JOIN volumes v ON sai.volume_id = v.id
        LEFT JOIN issues i ON sai.issue_id = i.id
        LEFT JOIN issues_files if ON sai.issue_id = if.issue_id
        WHERE sai.story_arc_id = ?
        GROUP BY sai.id
        ORDER BY sai.reading_order;
        """,
        (story_arc_id,)
    ).fetchalldict()


def replace_story_arc_issues(story_arc_id: int, issues: List[Any]) -> None:
    cursor = get_db()
    cursor.execute(
        "DELETE FROM story_arc_issues WHERE story_arc_id = ?;",
        (story_arc_id,)
    )
    for idx, issue in enumerate(issues, 1):
        if not isinstance(issue, dict):
            raise InvalidKeyValue('issues', issues)
        issue = _match_story_arc_issue(issue)
        cursor.execute(
            """
            INSERT INTO story_arc_issues(
                story_arc_id, reading_order, volume_id, issue_id,
                comicvine_issue_id, title, monitored
            ) VALUES (?,?,?,?,?,?,?);
            """,
            (
                story_arc_id,
                int(issue.get('reading_order') or idx),
                issue.get('volume_id'),
                issue.get('issue_id'),
                issue.get('comicvine_issue_id'),
                issue.get('title') or '',
                bool(issue.get('monitored', True))
            )
        )
    return


def get_story_arc_missing() -> List[Dict[str, Any]]:
    return get_db().execute(
        """
        SELECT
            sa.id AS story_arc_id,
            sa.title AS story_arc_title,
            sai.id AS story_arc_issue_id,
            sai.reading_order,
            sai.title AS issue_title,
            sai.volume_id,
            sai.issue_id,
            v.title AS volume_title,
            i.issue_number,
            i.date
        FROM story_arc_issues sai
        INNER JOIN story_arcs sa ON sai.story_arc_id = sa.id
        LEFT JOIN issues_files if ON sai.issue_id = if.issue_id
        LEFT JOIN volumes v ON sai.volume_id = v.id
        LEFT JOIN issues i ON sai.issue_id = i.id
        WHERE sa.monitored = 1
            AND sai.monitored = 1
            AND (sai.issue_id IS NULL OR if.issue_id IS NULL)
        GROUP BY sai.id
        ORDER BY sa.title, sai.reading_order;
        """
    ).fetchalldict()


# region Metadata previews and generation

def comicinfo_xml(volume_id: int, issue_id: Union[int, None] = None) -> str:
    volume = Library.get_volume(volume_id).get_public_data()
    issue = None
    if issue_id is not None:
        issue = next(
            (i for i in volume['issues'] if i['id'] == issue_id),
            None
        )
        if issue is None:
            raise InvalidKeyValue('issue_id', issue_id)

    root = Element('ComicInfo')
    SubElement(root, 'Series').text = volume['title']
    SubElement(root, 'Publisher').text = volume.get('publisher') or ''
    SubElement(root, 'Volume').text = str(volume.get('volume_number') or '')
    SubElement(root, 'Year').text = str(volume.get('year') or '')
    SubElement(root, 'Web').text = volume.get('site_url') or ''
    if issue:
        SubElement(root, 'Number').text = str(issue.get('issue_number') or '')
        SubElement(root, 'Title').text = issue.get('title') or ''
        if issue.get('date'):
            parts = issue['date'].split('-')
            if len(parts) >= 3:
                SubElement(root, 'Day').text = parts[2]
                SubElement(root, 'Month').text = parts[1]
                SubElement(root, 'Year').text = parts[0]
        SubElement(root, 'Summary').text = issue.get('description') or ''
    else:
        SubElement(root, 'Summary').text = volume.get('description') or ''

    return tostring(root, encoding='unicode')


def series_json(volume_id: int) -> Dict[str, Any]:
    volume = Library.get_volume(volume_id).get_public_data()
    return {
        'comicvine_id': volume['comicvine_id'],
        'title': volume['title'],
        'publisher': volume.get('publisher'),
        'year': volume.get('year'),
        'volume_number': volume.get('volume_number'),
        'site_url': volume.get('site_url'),
        'issues': [
            {
                'comicvine_id': i['comicvine_id'],
                'issue_number': i['issue_number'],
                'title': i['title'],
                'date': i['date'],
                'monitored': i['monitored'],
                'downloaded': bool(i['files'])
            }
            for i in volume['issues']
        ]
    }


def _metadata_profile_for_volume(volume_id: int) -> Dict[str, Any]:
    volume = Library.get_volume(volume_id).get_data()
    profile = get_profile(volume.quality_profile_id)
    metadata_profile = profile.get('metadata_profile') or DEFAULT_METADATA_PROFILE
    if not isinstance(metadata_profile, dict):
        return DEFAULT_METADATA_PROFILE
    return {**DEFAULT_METADATA_PROFILE, **metadata_profile}


def _can_write_metadata(filepath: str, preserve_existing: bool) -> bool:
    from os.path import exists
    return not (preserve_existing and exists(filepath))


def write_comicinfo_xml(
    volume_id: int,
    issue_id: Union[int, None] = None
) -> Dict[str, Any]:
    volume = Library.get_volume(volume_id).get_data()
    metadata_profile = _metadata_profile_for_volume(volume_id)
    create_folder(volume.folder)
    filename = 'ComicInfo.xml'
    if issue_id is not None:
        issue = Library.get_issue(issue_id).get_data()
        filename = f'ComicInfo_{issue.issue_number}.xml'
    filepath = join(volume.folder, filename)
    written = False
    if _can_write_metadata(filepath, metadata_profile['preserve_existing']):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(comicinfo_xml(volume_id, issue_id))
        written = True
    return {
        'filepath': filepath,
        'written': written,
        'metadata': comicinfo_xml(volume_id, issue_id)
    }


def write_series_json(volume_id: int) -> Dict[str, Any]:
    volume = Library.get_volume(volume_id).get_data()
    metadata_profile = _metadata_profile_for_volume(volume_id)
    create_folder(volume.folder)
    filepath = join(volume.folder, 'series.json')
    written = False
    if _can_write_metadata(filepath, metadata_profile['preserve_existing']):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(dumps(series_json(volume_id), indent=2))
        written = True
    return {
        'filepath': filepath,
        'written': written,
        'metadata': series_json(volume_id)
    }


def write_volume_metadata(volume_id: int) -> Dict[str, Any]:
    metadata_profile = _metadata_profile_for_volume(volume_id)
    files: List[Dict[str, Any]] = []
    if metadata_profile.get('write_comicinfo', True):
        files.append({
            'type': 'comicinfo',
            **write_comicinfo_xml(volume_id)
        })
    if metadata_profile.get('write_series_json', True):
        files.append({
            'type': 'series_json',
            **write_series_json(volume_id)
        })
    return {
        'volume_id': volume_id,
        'metadata_profile': metadata_profile,
        'files': files
    }
