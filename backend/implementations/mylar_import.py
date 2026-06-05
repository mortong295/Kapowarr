# -*- coding: utf-8 -*-

from json import loads
from typing import Any, Dict, Iterable, List, Mapping, Union

from backend.base.custom_exceptions import KapowarrException, VolumeAlreadyAdded
from backend.base.definitions import MonitorScheme
from backend.implementations.arr_features import (get_default_profile_id,
                                                  save_pull_list_item,
                                                  save_story_arc)
from backend.implementations.volumes import Library


def _as_mapping(data: Any) -> Mapping[str, Any]:
    return data if isinstance(data, dict) else {}


def _as_list(data: Any) -> List[Any]:
    return data if isinstance(data, list) else []


def _first(data: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ''):
            return value
    return ''


def _to_int(value: Any) -> Union[int, None]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any, default: bool = True) -> bool:
    if value in (None, ''):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in (
        '0', 'false', 'no', 'paused', 'ignored', 'unmonitored'
    )


def _records(parsed: Mapping[str, Any], *keys: str) -> List[Any]:
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, list):
            return value
    return []


def _volume_from_mylar(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        'comicvine_id': _to_int(_first(
            row,
            'ComicID',
            'comicid',
            'comicvine_id',
            'cv_id',
            'id'
        )),
        'title': _first(row, 'ComicName', 'comicname', 'title', 'name'),
        'year': _to_int(_first(row, 'ComicYear', 'year', 'start_year')),
        'publisher': _first(row, 'Publisher', 'publisher'),
        'folder': _first(row, 'ComicLocation', 'Location', 'folder', 'path'),
        'monitored': _to_bool(_first(
            row,
            'Status',
            'status',
            'monitored',
            'watching'
        )),
        'monitor_new_issues': _to_bool(_first(
            row,
            'MonitorNew',
            'monitor_new_issues'
        )),
        'root_folder': _first(row, 'RootFolder', 'root_folder')
    }


def _pull_item_from_mylar(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        'release_date': _first(
            row,
            'IssueDate',
            'ReleaseDate',
            'release_date',
            'date',
            'store_date'
        ),
        'publisher': _first(row, 'Publisher', 'publisher'),
        'series': _first(row, 'ComicName', 'Series', 'series', 'title'),
        'issue_number': _first(
            row,
            'Issue_Number',
            'IssueNumber',
            'issue_number',
            'number'
        ),
        'title': _first(row, 'IssueName', 'issue_title', 'subtitle', 'name'),
        'status': _first(row, 'Status', 'status') or 'pending'
    }


def _story_arc_from_mylar(row: Mapping[str, Any]) -> Dict[str, Any]:
    issues = [
        _pull_item_from_mylar(_as_mapping(issue))
        for issue in _as_list(_first(
            row,
            'issues',
            'IssueList',
            'entries',
            'reading_order'
        ))
    ]
    return {
        'title': _first(row, 'StoryName', 'ArcName', 'name', 'title'),
        'description': _first(row, 'description', 'Description'),
        'monitored': _to_bool(_first(row, 'monitored', 'Status')),
        'issues': issues
    }


def _normalise_payload(data: Union[str, Mapping[str, Any], List[Any]]) -> Any:
    if isinstance(data, str):
        return loads(data or '{}')
    return data


def parse_mylar_export(
    data: Union[str, Mapping[str, Any], List[Any]]
) -> Dict[str, Any]:
    """Parse common Mylar export/API/database-shaped records.

    This is deliberately preview-only: callers can show the normalized migration
    plan before applying anything to the Kapowarr library.
    """
    parsed = _normalise_payload(data)
    if isinstance(parsed, list):
        parsed = {'comics': parsed}
    parsed_map = _as_mapping(parsed)

    volumes = [
        volume
        for volume in (
            _volume_from_mylar(_as_mapping(row))
            for row in _records(
                parsed_map,
                'comics',
                'watchlist',
                'series',
                'watch_list'
            )
        )
        if volume['title'] or volume['comicvine_id']
    ]
    pull_list = [
        item
        for item in (
            _pull_item_from_mylar(_as_mapping(row))
            for row in _records(
                parsed_map,
                'pull_list',
                'pullist',
                'weekly',
                'issues',
                'wanted'
            )
        )
        if item['series']
    ]
    story_arcs = [
        arc
        for arc in (
            _story_arc_from_mylar(_as_mapping(row))
            for row in _records(
                parsed_map,
                'story_arcs',
                'storyarcs',
                'reading_lists',
                'readinglists'
            )
        )
        if arc['title']
    ]
    root_folders = sorted({
        str(volume['root_folder'] or volume['folder']).strip()
        for volume in volumes
        if str(volume['root_folder'] or volume['folder']).strip()
    })

    warnings: List[str] = []
    if not volumes:
        warnings.append('No Mylar watchlist/comic records were found.')
    if not pull_list:
        warnings.append('No Mylar pull-list/wanted issue records were found.')

    return {
        'volumes': volumes,
        'pull_list': pull_list,
        'story_arcs': story_arcs,
        'root_folders': root_folders,
        'summary': {
            'volumes': len(volumes),
            'pull_list_items': len(pull_list),
            'story_arcs': len(story_arcs),
            'root_folders': len(root_folders)
        },
        'warnings': warnings
    }


def _apply_bool_option(
    options: Mapping[str, Any],
    key: str,
    default: bool
) -> bool:
    value = options.get(key)
    return value if isinstance(value, bool) else default


def apply_mylar_export(
    data: Union[str, Mapping[str, Any], List[Any]],
    options: Mapping[str, Any]
) -> Dict[str, Any]:
    """Apply a parsed Mylar export to Kapowarr.

    Volumes are only added when a ComicVine ID is available, because Kapowarr's
    authoritative volume creation path is ComicVine-backed. Pull-list and story
    arc rows are imported through the existing ARR feature helpers so matching,
    monitoring and validation remain consistent with manual entry.
    """
    parsed = parse_mylar_export(data)
    root_folder_id = _to_int(options.get('root_folder_id'))
    quality_profile_id = (
        _to_int(options.get('quality_profile_id'))
        or get_default_profile_id()
    )
    monitor = _apply_bool_option(options, 'monitor', True)
    monitor_new_issues = _apply_bool_option(options, 'monitor_new_issues', True)
    auto_search = _apply_bool_option(options, 'auto_search', False)
    add_volumes = _apply_bool_option(options, 'add_volumes', True)
    import_pull_list = _apply_bool_option(options, 'import_pull_list', True)
    import_story_arcs = _apply_bool_option(options, 'import_story_arcs', True)
    use_custom_folders = _apply_bool_option(options, 'use_custom_folders', False)
    provider_name = str(options.get('provider') or 'Mylar Migration').strip()

    try:
        monitor_scheme = MonitorScheme(
            options.get('monitoring_scheme') or MonitorScheme.ALL.value
        )
    except ValueError:
        monitor_scheme = MonitorScheme.ALL

    results: Dict[str, Any] = {
        'preview': parsed,
        'summary': {
            'volumes_added': 0,
            'volumes_existing': 0,
            'volumes_skipped': 0,
            'pull_list_items': 0,
            'story_arcs': 0,
            'errors': 0
        },
        'volumes': [],
        'pull_list': [],
        'story_arcs': [],
        'errors': []
    }

    for volume in parsed['volumes']:
        if not add_volumes:
            results['summary']['volumes_skipped'] += 1
            continue
        if not volume.get('comicvine_id'):
            results['summary']['volumes_skipped'] += 1
            results['errors'].append({
                'type': 'volume',
                'title': volume.get('title'),
                'message': 'Skipped volume without a ComicVine ID.'
            })
            continue
        if root_folder_id is None:
            results['summary']['volumes_skipped'] += 1
            results['errors'].append({
                'type': 'volume',
                'title': volume.get('title'),
                'comicvine_id': volume.get('comicvine_id'),
                'message': 'Skipped volume because root_folder_id was not set.'
            })
            continue

        try:
            volume_id = Library.add(
                volume['comicvine_id'],
                root_folder_id,
                bool(volume.get('monitored', monitor)),
                monitor_scheme,
                bool(volume.get('monitor_new_issues', monitor_new_issues)),
                volume.get('folder') if use_custom_folders else None,
                None,
                auto_search,
                quality_profile_id
            )
        except VolumeAlreadyAdded as e:
            results['summary']['volumes_existing'] += 1
            results['volumes'].append({
                'status': 'existing',
                'comicvine_id': volume.get('comicvine_id'),
                'volume_id': e.volume_id,
                'title': volume.get('title')
            })
        except KapowarrException as e:
            results['summary']['errors'] += 1
            results['errors'].append({
                'type': 'volume',
                'title': volume.get('title'),
                'comicvine_id': volume.get('comicvine_id'),
                'message': str(e)
            })
        else:
            results['summary']['volumes_added'] += 1
            results['volumes'].append({
                'status': 'added',
                'comicvine_id': volume.get('comicvine_id'),
                'volume_id': volume_id,
                'title': volume.get('title')
            })

    if import_pull_list:
        for item in parsed['pull_list']:
            saved = save_pull_list_item({
                **item,
                'provider': provider_name
            })
            results['summary']['pull_list_items'] += 1
            results['pull_list'].append(saved)

    if import_story_arcs:
        for arc in parsed['story_arcs']:
            saved = save_story_arc(arc)
            results['summary']['story_arcs'] += 1
            results['story_arcs'].append(saved)

    return results
