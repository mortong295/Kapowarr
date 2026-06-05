# -*- coding: utf-8 -*-

from json import loads
from typing import Any, Dict, Iterable, List, Mapping, Union


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
