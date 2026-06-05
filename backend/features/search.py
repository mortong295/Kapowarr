# -*- coding: utf-8 -*-

from asyncio import gather, run
from urllib.parse import parse_qs, urljoin, urlparse
from xml.etree import ElementTree
from typing import Any, Dict, List, Mapping, Tuple, Union

from backend.base.custom_exceptions import InvalidKeyValue
from backend.base.definitions import (FileConstants, QUERY_FORMATS,
                                      DownloadSource,
                                      MatchedSearchResultData,
                                      SearchResultData, SearchSource,
                                      SpecialVersion)
from backend.base.file_extraction import (extract_filename_data,
                                      refine_special_version)
from backend.base.helpers import (AsyncSession, check_overlapping_issues,
                                  extract_year_from_date, force_range,
                                  normalise_query_string)
from backend.base.logging import LOGGER
from backend.implementations.external_indexers import search_external_indexers
from backend.implementations.getcomics import search_getcomics
from backend.implementations.matching import check_search_result_match
from backend.implementations.volumes import Volume


QUALITY_FORMATS = ('cbz', 'cbr', 'pdf', 'epub')
QUALITY_FORMAT_ALIASES = {
    'comic book zip': 'cbz',
    'zip': 'cbz',
    'comic book rar': 'cbr',
    'rar': 'cbr',
    'pdf': 'pdf',
    'epub': 'epub'
}
QUALITY_RANKS = {
    'preferred': 'Preferred',
    'allowed': 'Allowed',
    'unknown': 'Unknown',
    'rejected': 'Rejected'
}


def _normalise_quality_terms(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []

    return [
        str(v).strip().lower()
        for v in value
        if str(v).strip()
    ]


def _detect_quality_format(result: SearchResultData) -> str:
    haystack = ' '.join((
        result.get('display_title') or '',
        result.get('link') or '',
        result.get('source') or ''
    )).lower()

    for fmt in QUALITY_FORMATS:
        if f'.{fmt}' in haystack or f' {fmt}' in haystack:
            return fmt

    for alias, fmt in QUALITY_FORMAT_ALIASES.items():
        if alias in haystack:
            return fmt

    return 'unknown'


def _score_quality_profile(
    result: SearchResultData,
    profile: Mapping[str, Any]
) -> Dict[str, Any]:
    quality_format = _detect_quality_format(result)
    allowed_formats = _normalise_quality_terms(profile.get('allowed_formats'))
    preferred_formats = _normalise_quality_terms(
        profile.get('preferred_formats')
    )
    custom_formats = profile.get('custom_formats') or {}
    if not isinstance(custom_formats, dict):
        custom_formats = {}

    score = 0
    issue = None
    quality_rank = 'unknown'
    profile_match = True

    if quality_format != 'unknown':
        if allowed_formats and quality_format not in allowed_formats:
            profile_match = False
            issue = f'{quality_format.upper()} is not allowed by profile'
            quality_rank = 'rejected'
        elif quality_format in preferred_formats:
            score += 100
            quality_rank = 'preferred'
        else:
            quality_rank = 'allowed'

    haystack = ' '.join((
        result.get('display_title') or '',
        result.get('link') or '',
        result.get('source') or ''
    )).lower()
    for name, value in custom_formats.items():
        token = str(name).strip().lower()
        if not token or token not in haystack:
            continue
        try:
            score += int(value)
        except (TypeError, ValueError):
            continue

    if issue is None:
        if quality_rank == 'unknown':
            issue = 'Format could not be detected from provider title'
        else:
            issue = None

    return {
        'quality_profile_match': profile_match,
        'quality_profile_issue': issue,
        'quality_profile_id': profile.get('id') or 0,
        'quality_profile_name': profile.get('name') or 'Unknown Profile',
        'quality_format': quality_format,
        'quality_score': score,
        'quality_rank': QUALITY_RANKS[quality_rank]
    }


def _score_for_volume_profile(
    result: SearchResultData,
    quality_profile_id: int
) -> Dict[str, Any]:
    try:
        from backend.implementations.arr_features import get_profile
        profile = get_profile(quality_profile_id)
    except (InvalidKeyValue, KeyError, RuntimeError, TypeError, ValueError):
        profile = {
            'id': 0,
            'name': 'Unknown Profile',
            'allowed_formats': [],
            'preferred_formats': [],
            'custom_formats': {}
        }

    return _score_quality_profile(result, profile)


def _rank_search_result(
    result: MatchedSearchResultData,
    title: str,
    volume_number: int,
    year: Tuple[Union[int, None], Union[int, None]] = (None, None),
    calculated_issue_number: Union[float, None] = None
) -> List[int]:
    """Give a search result a rank, based on which you can sort.

    Args:
        result (MatchedSearchResultData): A search result.

        title (str): Title of volume.

        volume_number (int): The volume number of the volume.

        year (Tuple[Union[int, None], Union[int, None]], optional): The year of
        the volume and the year of the issue if searching for an issue and
        release date is known.
            Defaults to (None, None).

        calculated_issue_number (Union[float, None], optional): The
        calculated_issue_number of the issue.
            Defaults to None.

    Returns:
        List[int]: A list of numbers which determines the ranking of the result.
    """
    rating = []

    # Prefer matches (False == 0 == higher rank)
    rating.append(not result['match'])

    # Prefer results that satisfy the volume quality profile. Higher quality
    # scores rank before lower scores, Radarr/Sonarr-style.
    rating.append(not result.get('quality_profile_match', True))
    rating.append(-int(result.get('quality_score', 0)))

    # The more words in the search term that are present in
    # the search results' title, the higher ranked it gets
    split_title = title.split(' ')
    rating.append(len([
        word
        for word in result['series'].split(' ')
        if word not in split_title
    ]))

    # Prefer volume number or year matches, even better if both match
    vy_score = 3
    if (
        result['volume_number'] is not None
        and result['volume_number'] == volume_number
    ):
        vy_score -= 1

    if (
        year[1] is not None
        and result['year'] is not None
        and year[1] == result['year']
    ):
        # issue year direct match
        vy_score -= 2

    elif (
        year[0] is not None
        and year[1] is not None
        and result['year'] is not None
        and year[0] - 1 <= result['year'] <= year[1] + 1
    ):
        # fuzzy match between start year and issue year
        vy_score -= 1

    rating.append(vy_score)

    # Sort on issue number fitting
    if calculated_issue_number is not None:
        # Search was for issue
        if (
            isinstance(result['issue_number'], float)
            and calculated_issue_number == result['issue_number']
        ):
            # Issue number is direct match
            rating.append(0)

        elif isinstance(result['issue_number'], tuple):
            if (
                result['issue_number'][0]
                <= calculated_issue_number
                <= result['issue_number'][1]
            ):
                # Issue number falls between range
                rating.append(
                    1 - (1 / (
                        result['issue_number'][1] - result['issue_number'][0] + 1
                    ))
                )

            else:
                # Issue number falls outside so release is not useful
                rating.append(3)

        elif result['special_version'] is not None:
            # Issue number not found but is special version
            rating.append(2)

        else:
            # No issue number found and not special version
            rating.append(3)

    else:
        # Search was for volume
        if isinstance(result['issue_number'], tuple):
            rating.append(
                1.0
                /
                (result['issue_number'][1] - result['issue_number'][0] + 1)
            )

        elif isinstance(result['issue_number'], float):
            rating.append(1)

    return rating


class SearchGetComics(SearchSource):
    async def search(self, session: AsyncSession) -> List[SearchResultData]:
        return await search_getcomics(session, self.query)


class SearchExternalIndexers(SearchSource):
    async def search(self, session: AsyncSession) -> List[SearchResultData]:
        return await search_external_indexers(session, self.query)


def _normalise_indexer_implementation(indexer: Mapping[str, Any]) -> str:
    return str(indexer.get('implementation') or '').strip().lower()


def _normalise_indexer_settings(indexer: Mapping[str, Any]) -> Mapping[str, Any]:
    settings = indexer.get('settings') or {}
    return settings if isinstance(settings, dict) else {}


def _rss_items(feed_body: str) -> List[Dict[str, str]]:
    if not feed_body:
        return []

    try:
        root = ElementTree.fromstring(feed_body)
    except ElementTree.ParseError:
        return []

    items: List[Dict[str, str]] = []
    for item in root.findall('.//item'):
        title = item.findtext('title') or ''
        link = item.findtext('link') or item.findtext('guid') or ''
        if not title or not link:
            continue
        items.append({'title': title.strip(), 'link': link.strip()})

    for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
        title = entry.findtext('{http://www.w3.org/2005/Atom}title') or ''
        link = ''
        link_el = entry.find('{http://www.w3.org/2005/Atom}link')
        if link_el is not None:
            link = link_el.attrib.get('href') or ''
        if not link:
            link = entry.findtext('{http://www.w3.org/2005/Atom}id') or ''
        if not title or not link:
            continue
        items.append({'title': title.strip(), 'link': link.strip()})

    return items


def _query_matches_title(query: str, title: str) -> bool:
    query_terms = [
        term.lower()
        for term in normalise_query_string(query).split(' ')
        if term.strip()
    ]
    title_lower = title.lower()
    return all(term in title_lower for term in query_terms)


def _transport_from_link(link: str) -> Dict[str, str]:
    link_lower = link.lower()
    if link_lower.startswith('magnet:'):
        return {
            'download_type': 'torrent',
            'source_type': DownloadSource.TORRENT.value
        }

    parsed = urlparse(link_lower)
    query = parse_qs(parsed.query)
    if query.get('t', [''])[0] == 'get' or '.nzb' in link_lower:
        return {
            'download_type': 'usenet',
            'source_type': DownloadSource.USENET.value
        }

    if '.torrent' in link_lower:
        return {
            'download_type': 'torrent',
            'source_type': DownloadSource.TORRENT.value
        }

    if any(
        parsed.path.endswith(ext.lower())
        for ext in FileConstants.CONTAINER_EXTENSIONS
    ):
        return {
            'download_type': 'direct',
            'source_type': DownloadSource.DIRECT.value
        }

    return {}


def _format_indexer_result(
    indexer: Mapping[str, Any],
    title: str,
    link: str,
    download_type: Union[str, None] = None
) -> SearchResultData:
    implementation = _normalise_indexer_implementation(indexer)
    source = str(indexer.get('name') or implementation or '')
    transport = _transport_from_link(link)
    if download_type:
        source_type = {
            'direct': DownloadSource.DIRECT,
            'torrent': DownloadSource.TORRENT,
            'usenet': DownloadSource.USENET
        }.get(download_type)
        if source_type:
            transport = {
                'download_type': download_type,
                'source_type': source_type.value
            }

    return {
        **extract_filename_data(
            title,
            assume_volume_number=False,
            fix_year=True
        ),
        'link': link,
        'display_title': title,
        'source': source,
        'source_name': source,
        **transport
    }


async def _search_rss_indexer(
    session: AsyncSession,
    query: str,
    indexer: Mapping[str, Any]
) -> List[SearchResultData]:
    settings = _normalise_indexer_settings(indexer)
    feed_url = settings.get('url') or settings.get('feed_url')
    if not isinstance(feed_url, str) or not feed_url.strip():
        return []

    feed_body = await session.get_text(feed_url.strip(), quiet_fail=True)
    return [
        _format_indexer_result(indexer, item['title'], item['link'])
        for item in _rss_items(feed_body)
        if _query_matches_title(query, item['title'])
    ]


async def _search_newznab_indexer(
    session: AsyncSession,
    query: str,
    indexer: Mapping[str, Any]
) -> List[SearchResultData]:
    settings = _normalise_indexer_settings(indexer)
    base_url = settings.get('base_url') or settings.get('url')
    api_key = settings.get('api_key') or settings.get('apikey')
    if not isinstance(base_url, str) or not base_url.strip():
        return []

    params: Dict[str, Any] = {'t': 'search', 'q': query, 'o': 'xml'}
    if isinstance(api_key, str) and api_key.strip():
        params['apikey'] = api_key.strip()
    if settings.get('categories'):
        params['cat'] = str(settings['categories'])

    feed_body = await session.get_text(
        urljoin(base_url.rstrip('/') + '/', 'api'),
        params=params,
        quiet_fail=True
    )
    return [
        _format_indexer_result(
            indexer,
            item['title'],
            item['link'],
            'torrent' if _normalise_indexer_implementation(indexer) == 'torznab'
            else 'usenet'
        )
        for item in _rss_items(feed_body)
    ]


async def _search_indexer(
    session: AsyncSession,
    query: str,
    indexer: Mapping[str, Any]
) -> List[SearchResultData]:
    implementation = _normalise_indexer_implementation(indexer)
    if implementation == 'getcomics':
        results = await search_getcomics(session, query)
        for result in results:
            result['source'] = indexer.get('name') or result['source']
        return results

    if implementation == 'rawrss':
        return await _search_rss_indexer(session, query, indexer)

    if implementation in ('newznab', 'torznab'):
        return await _search_newznab_indexer(session, query, indexer)

    return []


def _get_enabled_indexers() -> List[Dict[str, Any]]:
    try:
        from backend.implementations.arr_features import get_providers
        return [
            indexer
            for indexer in get_providers('indexers')
            if indexer.get('enabled')
        ]
    except (InvalidKeyValue, KeyError, RuntimeError, TypeError, ValueError):
        return [{
            'id': 0,
            'name': 'GetComics',
            'implementation': 'getcomics',
            'enabled': True,
            'priority': 25,
            'settings': {},
            'tags': []
        }]


async def search_multiple_queries(*queries: str) -> List[SearchResultData]:
    """Do a manual search for multiple queries asynchronously.

    Returns:
        List[SearchResultData]: The search results for all queries together,
        duplicates removed.
    """
    indexers = _get_enabled_indexers()
    async with AsyncSession() as session:
        searches = [
            _search_indexer(session, query, indexer)
            for indexer in indexers
            for query in queries
        ] + [
            search_external_indexers(session, query)
            for query in queries
        ]
        responses = await gather(*searches) if searches else []

    search_results: List[SearchResultData] = []
    processed_links = set()
    for response in responses:
        for result in response:
            # Don't add if the link is already in the results
            # Avoids duplicates, as multiple formats can return the same result
            if result['link'] not in processed_links:
                search_results.append(result)
                processed_links.add(result['link'])

    return search_results


def manual_search(
    volume_id: int,
    issue_id: Union[int, None] = None
) -> List[MatchedSearchResultData]:
    """Do a manual search for a volume or issue.

    Args:
        volume_id (int): The id of the volume to search for.
        issue_id (Union[int, None], optional): The id of the issue to search for,
        in the case that you want to search for an issue instead of a volume.
            Defaults to None.

    Returns:
        List[MatchedSearchResultData]: List with search results.
    """
    volume = Volume(volume_id)
    volume_data = volume.get_data()
    volume_issues = volume.get_issues()
    number_to_year: Dict[float, Union[int, None]] = {
        i.calculated_issue_number: extract_year_from_date(i.date)
        for i in volume_issues
    }
    issue_number: Union[str, None] = None
    calculated_issue_number: Union[float, None] = None

    if issue_id and volume_data.special_version in (
        SpecialVersion.NORMAL,
        SpecialVersion.VOLUME_AS_ISSUE
    ):
        issue_data = volume.get_issue(issue_id).get_data()
        issue_number = issue_data.issue_number
        calculated_issue_number = issue_data.calculated_issue_number

    LOGGER.info(
        'Starting manual search: %s (%d) %s',
        volume_data.title, volume_data.year,
        f'#{issue_number}' if issue_number else ''
    )

    for title in (volume_data.title, volume_data.alt_title):
        if not title:
            continue

        if volume_data.special_version == SpecialVersion.TPB:
            formats = QUERY_FORMATS["TPB"]

        elif volume_data.special_version == SpecialVersion.VOLUME_AS_ISSUE:
            formats = QUERY_FORMATS["VAI"]

        elif issue_number is None:
            formats = QUERY_FORMATS["Volume"]

        else:
            formats = QUERY_FORMATS["Issue"]

        if volume_data.year is None:
            formats = tuple(
                f.replace('({year})', '').strip()
                for f in formats
            )

        search_title = normalise_query_string(title).replace(':', '')
        search_results = run(search_multiple_queries(*(
            format.format(
                title=search_title, volume_number=volume_data.volume_number,
                year=volume_data.year, issue_number=issue_number
            )
            for format in formats
        )))
        if not search_results:
            continue

        results: List[MatchedSearchResultData] = []
        for result in search_results:
            match = check_search_result_match(
                result, volume_data, volume_issues,
                number_to_year, calculated_issue_number
            )
            quality = _score_for_volume_profile(
                result, volume_data.quality_profile_id
            )
            results.append({
                **result,
                **match,
                **quality
            })

        # Sort results; put best result at top
        results.sort(key=lambda r: _rank_search_result(
            r, search_title, volume_data.volume_number,
            (
                volume_data.year,
                number_to_year.get(calculated_issue_number) # type: ignore
            ),
            calculated_issue_number
        ))

        LOGGER.debug('Manual search results: %s', results)
        return results

    return []


def auto_search(
    volume_id: int,
    issue_id: Union[int, None] = None
) -> List[MatchedSearchResultData]:
    """Search for a volume or issue and automatically choose a result.

    Args:
        volume_id (int): The ID of the volume to search for.
        issue_id (Union[int, None], optional): The id of the issue to search for,
        in the case that you want to search for an issue instead of a volume.
            Defaults to None.

    Returns:
        List[MatchedSearchResultData]: List with chosen search results.
    """
    volume = Volume(volume_id)
    volume_data = volume.get_data()
    volume_issues = volume.get_issues(_skip_files=True)
    volume_issues.sort(key=lambda i: i.calculated_issue_number)
    LOGGER.info(
        'Starting auto search for volume %d %s',
        volume_id,
        f'issue {issue_id}' if issue_id else ''
    )

    searchable_issues: List[Tuple[int, float]] = []
    if not volume_data.monitored:
        # Volume is unmonitored so don't auto search
        pass

    elif issue_id is None:
        # Auto search volume
        # Get open issues (monitored and no file).
        searchable_issues = volume.get_open_issues()

    else:
        # Auto search issue
        issue = volume.get_issue(issue_id)
        issue_data = issue.get_data()
        if issue_data.monitored and not issue.get_files():
            # Issue is open
            searchable_issues = [(issue_id, issue_data.calculated_issue_number)]

    if not searchable_issues:
        # No issues to search for
        result = []
        LOGGER.debug(f'Auto search results: {result}')
        return result

    search_results = [
        r
        for r in manual_search(volume_id, issue_id)
        if r['match'] and r.get('quality_profile_match', True)
    ]

    if issue_id is not None or volume_data.special_version not in (
        SpecialVersion.NORMAL,
        SpecialVersion.VOLUME_AS_ISSUE
    ):
        # We're searching for one "item", so just grab first search result.
        result = search_results[:1] if search_results else []
        LOGGER.debug('Auto search results: %s', result)
        return result

    # We're searching for a volume, so we might download multiple search results.
    # Find a combination of search results that download the most issues.
    chosen_downloads: List[MatchedSearchResultData] = []
    searchable_issue_numbers = {i[1] for i in searchable_issues}
    for result in search_results:
        result = refine_special_version(volume_data, result)

        # Determine what issues the result covers
        if result["special_version"]:
            result["issue_number"] = 1.0
            covered_issues = volume_issues

        elif result["issue_number"] is not None:
            if isinstance(result["issue_number"], tuple):
                n_start, n_end = result["issue_number"]
            else:
                n_start, n_end = force_range(result["issue_number"])

            covered_issues = [
                issue
                for issue in volume_issues
                if n_start <= issue.calculated_issue_number <= n_end
            ]

        else:
            continue

        if any(
            i.calculated_issue_number not in searchable_issue_numbers
            for i in covered_issues
        ):
            # Part or all of what the result covers is already downloaded
            continue

        # Check that any other selected download doesn't already cover the issue
        for part in chosen_downloads:
            if check_overlapping_issues(
                part["issue_number"], # type: ignore
                result["issue_number"]
            ):
                break
        else:
            chosen_downloads.append(result)

    # Find issues that have still not been covered. Might've been that the
    # download for the issue simply did not pop up on volume search, but will
    # when searching for the individual issue.
    missing_issues = [
        i
        for i in searchable_issues
        if not any(
            check_overlapping_issues(
                i[1], part["issue_number"] # type: ignore
            )
            for part in chosen_downloads
        )
    ]

    for missing_issue in missing_issues:
        chosen_downloads.extend(auto_search(volume_id, missing_issue[0]))

    LOGGER.debug('Auto search results: %s', chosen_downloads)
    return chosen_downloads
