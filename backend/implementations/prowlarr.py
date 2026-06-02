# -*- coding: utf-8 -*-

from datetime import datetime
from re import sub
from typing import Any, Dict, List, Mapping, Sequence, Tuple, Union
from urllib.parse import urljoin

from aiohttp import ClientError
from requests.exceptions import RequestException

from backend.base.custom_exceptions import ClientNotWorking, CredentialInvalid
from backend.base.definitions import (BrokenClientReason, ClientTestResult,
                                      Constants, DownloadSource,
                                      SearchResultData)
from backend.base.file_extraction import extract_filename_data
from backend.base.helpers import AsyncSession, CommaList, Session, normalise_base_url
from backend.base.logging import LOGGER
from backend.internals.settings import Settings


class Prowlarr:
    """Small Prowlarr search proxy client."""

    def __init__(
        self,
        base_url: Union[str, None] = None,
        api_key: Union[str, None] = None,
        timeout: Union[int, None] = None,
        categories: Union[Sequence[str], None] = None
    ) -> None:
        settings = Settings().sv
        self.base_url = normalise_base_url(base_url or settings.prowlarr_base_url)
        self.api_key = api_key if api_key is not None else settings.prowlarr_api_key
        self.timeout = timeout or settings.prowlarr_timeout_seconds
        self.categories = list(categories or settings.prowlarr_comic_categories)
        return

    @property
    def enabled(self) -> bool:
        return (
            Settings().sv.prowlarr_enabled
            and bool(self.base_url and self.api_key)
        )

    @staticmethod
    def _headers(api_key: str) -> Dict[str, str]:
        return {'X-Api-Key': api_key, 'User-Agent': Constants.DEFAULT_USERAGENT}

    @classmethod
    def test(
        cls,
        base_url: str,
        api_key: str,
        timeout: int = Constants.REQUEST_TIMEOUT
    ) -> ClientTestResult:
        try:
            response = Session().get(
                f'{normalise_base_url(base_url)}/api/v1/system/status',
                headers=cls._headers(api_key),
                timeout=timeout
            )
        except RequestException:
            return {
                'success': False,
                'description': 'Failed to connect to Prowlarr'
            }

        if response.status_code in (401, 403):
            return {
                'success': False,
                'description': 'Failed to authenticate with Prowlarr'
            }
        if not response.ok:
            return {
                'success': False,
                'description': f'Prowlarr returned HTTP {response.status_code}'
            }
        try:
            version = response.json().get('version')
        except ValueError:
            return {
                'success': False,
                'description': 'Prowlarr returned an unexpected response'
            }
        return {
            'success': True,
            'description': f'Connected to Prowlarr {version or ""}'.strip()
        }

    async def search(
        self,
        session: AsyncSession,
        query: str
    ) -> List[SearchResultData]:
        if not self.enabled:
            return []

        params: Dict[str, Any] = {'query': query, 'type': 'search'}
        if self.categories:
            params['categories'] = ','.join(map(str, self.categories))

        LOGGER.info('Searching Prowlarr for query: %s', query)
        try:
            response = await session.get(
                f'{self.base_url}/api/v1/search',
                params=params,
                headers=self._headers(self.api_key),
                timeout=self.timeout
            )
        except ClientError:
            LOGGER.exception("Can't connect to Prowlarr instance")
            return []

        if response.status in (401, 403):
            LOGGER.warning('Prowlarr authentication failed')
            return []
        if not response.ok:
            LOGGER.warning('Prowlarr search returned HTTP %d', response.status)
            return []

        try:
            payload = await response.json()
        except Exception:
            LOGGER.warning('Prowlarr returned an unexpected search response')
            return []

        if not isinstance(payload, list):
            return []

        results = [r for r in (self._map_result(item) for item in payload) if r]
        LOGGER.info('Prowlarr returned %d Usenet results', len(results))
        return results

    @staticmethod
    def _download_type(item: Mapping[str, Any]) -> str:
        protocol = str(
            item.get('protocol')
            or item.get('downloadProtocol')
            or ''
        ).lower()
        if protocol == 'usenet':
            return 'usenet'
        if protocol == 'torrent':
            return 'torrent'
        download_url = str(
            item.get('downloadUrl')
            or item.get('download_url')
            or ''
        )
        if '.nzb' in download_url.lower() or 'getnzb' in download_url.lower():
            return 'usenet'
        return protocol

    @classmethod
    def _map_result(
        cls,
        item: Mapping[str, Any]
    ) -> Union[SearchResultData, None]:
        if cls._download_type(item) != 'usenet':
            return None
        title = str(item.get('title') or '')
        download_url = str(
            item.get('downloadUrl')
            or item.get('download_url')
            or ''
        )
        guid = str(item.get('guid') or item.get('infoUrl') or download_url)
        if not title or not download_url:
            return None
        parsed = extract_filename_data(title)
        return {
            **parsed,
            'link': download_url,
            'display_title': title,
            'source': DownloadSource.PROWLARR.value,
            'guid': guid,
            'indexer': item.get('indexer') or '',
            'indexer_id': item.get('indexerId'),
            'size': item.get('size') or 0,
            'publish_date': item.get('publishDate') or item.get('publish_date'),
            'category': item.get('categories') or item.get('category'),
            'protocol': item.get('protocol') or 'usenet',
            'download_type': 'usenet',
            'seeders': item.get('seeders'),
            'leechers': item.get('leechers')
        }


def normalise_release_title(title: str) -> str:
    title = title.lower().replace('&', ' and ')
    title = sub(r'\bthe\s+', '', title)
    title = sub(r'[^a-z0-9.]+', ' ', title)
    return sub(r'\s+', ' ', title).strip()


def score_release(
    result: Mapping[str, Any],
    series_title: str,
    issue_number: Union[float, None] = None,
    year: Union[int, None] = None,
    publisher: Union[str, None] = None,
    special_version: Union[str, None] = None
) -> Tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    release_title = normalise_release_title(str(result.get('display_title') or ''))
    series = normalise_release_title(series_title)
    if series and series in release_title:
        score += 40
        reasons.append('series title match')
    if issue_number is not None:
        parsed_issue = result.get('issue_number')
        if parsed_issue == issue_number:
            score += 30
            reasons.append('issue number match')
        elif (
            isinstance(parsed_issue, tuple)
            and parsed_issue[0] <= issue_number <= parsed_issue[1]
        ):
            score += 20
            reasons.append('issue number in pack range')
    if year and result.get('year') == year:
        score += 15
        reasons.append('year match')
    if publisher and normalise_release_title(publisher) in release_title:
        score += 5
        reasons.append('publisher match')
    if special_version and result.get('special_version') == special_version:
        score += 10
        reasons.append('format match')
    if any(
        term in release_title
        for term in ('sample', 'preview', 'french', 'german')
    ):
        score -= 20
        reasons.append('unwanted term')
    return max(0, min(100, score)), reasons
