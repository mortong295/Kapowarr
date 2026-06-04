# -*- coding: utf-8 -*-

from asyncio import gather
from json import loads
from sqlite3 import IntegrityError
from typing import Any, Dict, List, Mapping, Type, Union
from xml.etree import ElementTree

from aiohttp import ClientError
from requests.exceptions import RequestException

from backend.base.custom_exceptions import (ClientNotWorking,
                                            CredentialInvalid,
                                            InvalidKeyValue, KeyNotFound)
from backend.base.definitions import (BrokenClientReason, Constants,
                                      SearchResultData)
from backend.base.file_extraction import extract_filename_data
from backend.base.helpers import (AsyncSession, Session, get_subclasses,
                                  normalise_base_url)
from backend.base.logging import LOGGER
from backend.internals.db import get_db


class BaseExternalIndexer:
    indexer_type = ''
    required_tokens = ('title', 'base_url', 'api_key')

    @property
    def id(self) -> int:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def categories(self) -> Union[str, None]:
        return self._categories

    def __init__(self, indexer_id: int) -> None:
        self._id = indexer_id
        data = get_db().execute("""
            SELECT
                indexer_type, title, base_url,
                api_key, enabled, categories
            FROM external_indexers
            WHERE id = ?
            LIMIT 1;
            """,
            (indexer_id,)
        ).fetchone()
        self._title = data['title']
        self._base_url = data['base_url']
        self._api_key = data['api_key']
        self._enabled = bool(data['enabled'])
        self._categories = data['categories']
        return

    def get_indexer_data(self) -> Dict[str, Any]:
        return {
            'id': self._id,
            'indexer_type': self.indexer_type,
            'title': self._title,
            'base_url': self._base_url,
            'api_key': self._api_key,
            'enabled': self._enabled,
            'categories': self._categories
        }

    def update_indexer(self, data: Mapping[str, Any]) -> None:
        filtered_data = ExternalIndexers.prepare_data(
            self.indexer_type,
            data,
            existing_api_key=self._api_key
        )

        self.test(
            filtered_data['base_url'],
            filtered_data['api_key']
        )

        get_db().execute("""
            UPDATE external_indexers
            SET
                title = :title,
                base_url = :base_url,
                api_key = :api_key,
                enabled = :enabled,
                categories = :categories
            WHERE id = :id;
            """,
            {
                **filtered_data,
                "id": self._id
            }
        )
        self._title = filtered_data['title']
        self._base_url = filtered_data['base_url']
        self._api_key = filtered_data['api_key']
        self._enabled = filtered_data['enabled']
        self._categories = filtered_data['categories']
        return

    def delete_indexer(self) -> None:
        try:
            get_db().execute(
                "DELETE FROM external_indexers WHERE id = ?;",
                (self.id,)
            )
        except IntegrityError:
            raise InvalidKeyValue('id', self.id)
        return

    @classmethod
    def test(cls, base_url: str, api_key: str) -> None:
        raise NotImplementedError

    async def search(
        self,
        session: AsyncSession,
        query: str
    ) -> List[SearchResultData]:
        raise NotImplementedError


class NewznabIndexer(BaseExternalIndexer):
    indexer_type = 'Newznab'

    @staticmethod
    def _api_url(base_url: str) -> str:
        if base_url.rstrip('/').endswith('/api'):
            return base_url.rstrip('/')
        return f"{base_url.rstrip('/')}/api"

    @classmethod
    def test(cls, base_url: str, api_key: str) -> None:
        try:
            response = Session().get(
                cls._api_url(base_url),
                params={
                    't': 'caps',
                    'apikey': api_key,
                    'o': 'json'
                },
                timeout=30
            )
        except RequestException:
            raise ClientNotWorking(BrokenClientReason.CONNECTION_ERROR)

        if response.status_code in (401, 403):
            raise CredentialInvalid

        if not response.ok:
            raise ClientNotWorking(BrokenClientReason.NOT_CLIENT_INSTANCE)

        try:
            response.json()
            return
        except ValueError:
            pass

        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

        if root.tag.lower() == 'error':
            code = root.attrib.get('code', '')
            if code in ('100', '101'):
                raise CredentialInvalid
            raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

        return

    async def search(
        self,
        session: AsyncSession,
        query: str
    ) -> List[SearchResultData]:
        params = {
            't': 'search',
            'q': query,
            'apikey': self.api_key,
            'o': 'json'
        }
        if self.categories:
            params['cat'] = self.categories

        try:
            response_text = await session.get_text(
                self._api_url(self.base_url),
                params=params,
                quiet_fail=True
            )
        except ClientError:
            LOGGER.warning('Newznab search failed for %s', self.title)
            return []

        return self._format_results(response_text, self.title)

    @classmethod
    def _format_results(
        cls,
        response_text: str,
        source_name: str
    ) -> List[SearchResultData]:
        if not response_text:
            return []

        try:
            payload = loads(response_text)
        except ValueError:
            return cls._format_xml_results(response_text, source_name)

        items = (
            payload.get('channel', {}).get('item', [])
            if isinstance(payload, dict) else []
        )
        if isinstance(items, dict):
            items = [items]

        return [
            result
            for item in items
            for result in (cls._result_from_item(item, source_name),)
            if result is not None
        ]

    @classmethod
    def _format_xml_results(
        cls,
        response_text: str,
        source_name: str
    ) -> List[SearchResultData]:
        try:
            root = ElementTree.fromstring(response_text)
        except ElementTree.ParseError:
            return []

        if root.tag.lower() == 'error':
            return []

        return [
            result
            for item in root.findall('.//item')
            for result in (cls._result_from_xml_item(item, source_name),)
            if result is not None
        ]

    @staticmethod
    def _result_from_item(
        item: Mapping[str, Any],
        source_name: str
    ) -> Union[SearchResultData, None]:
        if not isinstance(item, Mapping):
            return None

        title = str(item.get('title') or '').strip()
        link = str(
            item.get('link')
            or item.get('downloadUrl')
            or item.get('download_url')
            or ''
        ).strip()
        if not title or not link:
            return None

        return {
            **extract_filename_data(
                title,
                assume_volume_number=False,
                fix_year=True
            ),
            'link': link,
            'display_title': title,
            'source': source_name
        }

    @staticmethod
    def _result_from_xml_item(
        item: ElementTree.Element,
        source_name: str
    ) -> Union[SearchResultData, None]:
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        if not title or not link:
            return None

        return {
            **extract_filename_data(
                title,
                assume_volume_number=False,
                fix_year=True
            ),
            'link': link,
            'display_title': title,
            'source': source_name
        }


class ProwlarrIndexer(BaseExternalIndexer):
    indexer_type = 'Prowlarr'

    @classmethod
    def test(cls, base_url: str, api_key: str) -> None:
        try:
            response = Session().get(
                f"{base_url.rstrip('/')}/api/v1/system/status",
                headers={'X-Api-Key': api_key},
                timeout=30
            )
        except RequestException:
            raise ClientNotWorking(BrokenClientReason.CONNECTION_ERROR)

        if response.status_code in (401, 403):
            raise CredentialInvalid

        if not response.ok:
            raise ClientNotWorking(BrokenClientReason.NOT_CLIENT_INSTANCE)

        try:
            result = response.json()
        except ValueError:
            raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

        if not isinstance(result, dict) or 'version' not in result:
            raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

        return

    async def search(
        self,
        session: AsyncSession,
        query: str
    ) -> List[SearchResultData]:
        params: Dict[str, Any] = {
            'query': query,
            'type': 'search'
        }
        if self.categories:
            params['categories'] = self.categories

        try:
            response_text = await session.get_text(
                f"{self.base_url.rstrip('/')}/api/v1/search",
                params=params,
                headers={'X-Api-Key': self.api_key},
                quiet_fail=True
            )
        except ClientError:
            LOGGER.warning('Prowlarr search failed for %s', self.title)
            return []

        try:
            payload = loads(response_text)
        except ValueError:
            return []

        if not isinstance(payload, list):
            return []

        return self._format_results(payload, self.title)

    @staticmethod
    def _format_results(
        results: List[Mapping[str, Any]],
        source_name: str
    ) -> List[SearchResultData]:
        formatted: List[SearchResultData] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue

            protocol = str(item.get('protocol') or '').lower()
            if protocol == 'torrent':
                continue

            title = str(item.get('title') or '').strip()
            link = str(
                item.get('downloadUrl')
                or item.get('download_url')
                or item.get('link')
                or item.get('guid')
                or ''
            ).strip()
            if not title or not link:
                continue

            formatted.append({
                **extract_filename_data(
                    title,
                    assume_volume_number=False,
                    fix_year=True
                ),
                'link': link,
                'display_title': title,
                'source': str(item.get('indexer') or source_name)
            })

        return formatted


class ExternalIndexers:
    @staticmethod
    def get_indexer_types() -> Dict[str, Type[BaseExternalIndexer]]:
        return {
            indexer.indexer_type: indexer
            for indexer in sorted(
                get_subclasses(BaseExternalIndexer),
                key=lambda c: c.indexer_type.lower()
            )
        }

    @staticmethod
    def prepare_data(
        indexer_type: str,
        data: Mapping[str, Any],
        existing_api_key: Union[str, None] = None
    ) -> Dict[str, Any]:
        try:
            IndexerClass = ExternalIndexers.get_indexer_types()[indexer_type]
        except KeyError:
            raise InvalidKeyValue('type', indexer_type)

        filtered_data: Dict[str, Any] = {}
        for key in (
            'title', 'base_url', 'api_key',
            'enabled', 'categories'
        ):
            if key in IndexerClass.required_tokens and key not in data:
                raise KeyNotFound(key)

            value = data.get(key)
            if key in IndexerClass.required_tokens and value is None:
                raise InvalidKeyValue(key, value)

            if key == 'base_url':
                filtered_data[key] = normalise_base_url(str(value))
            elif key == 'api_key' and value == Constants.CREDENTIAL_REPLACEMENT:
                if existing_api_key is None:
                    raise InvalidKeyValue(key, value)
                filtered_data[key] = existing_api_key
            elif key == 'enabled':
                filtered_data[key] = bool(True if value is None else value)
            elif key == 'categories':
                filtered_data[key] = ExternalIndexers.normalise_categories(value)
            elif isinstance(value, str):
                filtered_data[key] = value.strip()
            else:
                filtered_data[key] = value

        if not filtered_data['title']:
            raise InvalidKeyValue('title', filtered_data['title'])
        if not filtered_data['api_key']:
            raise InvalidKeyValue('api_key', filtered_data['api_key'])

        return filtered_data

    @staticmethod
    def normalise_categories(value: Any) -> Union[str, None]:
        if value is None:
            return None
        if isinstance(value, list):
            parts = [
                str(v).strip()
                for v in value
                if str(v).strip()
            ]
        elif isinstance(value, str):
            parts = [
                part.strip()
                for part in value.replace('\n', ',').split(',')
                if part.strip()
            ]
        else:
            raise InvalidKeyValue('categories', value)

        return ','.join(parts) or None

    @staticmethod
    def test(
        indexer_type: str,
        base_url: str,
        api_key: str
    ) -> Dict[str, Any]:
        try:
            IndexerClass = ExternalIndexers.get_indexer_types()[indexer_type]
        except KeyError:
            raise InvalidKeyValue('type', indexer_type)

        try:
            IndexerClass.test(normalise_base_url(base_url), api_key)
        except ClientNotWorking as e:
            return {
                'success': False,
                'description': e.reason_text
            }
        except CredentialInvalid:
            return {
                'success': False,
                'description': 'Failed to login with the given API key'
            }
        else:
            return {
                'success': True,
                'description': None
            }

    @staticmethod
    def add(
        indexer_type: str,
        title: str,
        base_url: str,
        api_key: str,
        enabled: bool = True,
        categories: Union[str, List[str], None] = None
    ) -> BaseExternalIndexer:
        filtered_data = ExternalIndexers.prepare_data(indexer_type, {
            'title': title,
            'base_url': base_url,
            'api_key': api_key,
            'enabled': enabled,
            'categories': categories
        })

        ExternalIndexers.get_indexer_types()[indexer_type].test(
            filtered_data['base_url'],
            filtered_data['api_key']
        )

        indexer_id = get_db().execute("""
            INSERT INTO external_indexers(
                indexer_type, title, base_url,
                api_key, enabled, categories
            ) VALUES (
                :indexer_type, :title, :base_url,
                :api_key, :enabled, :categories
            );
            """,
            {
                **filtered_data,
                'indexer_type': indexer_type
            }
        ).lastrowid
        return ExternalIndexers.get_indexer(indexer_id)

    @staticmethod
    def get_indexers() -> List[Dict[str, Any]]:
        return get_db().execute("""
            SELECT
                id, indexer_type, title, base_url,
                api_key, enabled, categories
            FROM external_indexers
            ORDER BY title, id;
            """
        ).fetchalldict()

    @staticmethod
    def get_indexer(indexer_id: int) -> BaseExternalIndexer:
        indexer_type = get_db().execute("""
            SELECT indexer_type
            FROM external_indexers
            WHERE id = ?
            LIMIT 1;
            """,
            (indexer_id,)
        ).exists()

        if not indexer_type:
            raise InvalidKeyValue('id', indexer_id)

        return ExternalIndexers.get_indexer_types()[indexer_type](indexer_id)

    @staticmethod
    def get_enabled_indexers() -> List[BaseExternalIndexer]:
        return [
            ExternalIndexers.get_indexer(indexer['id'])
            for indexer in ExternalIndexers.get_indexers()
            if indexer['enabled']
        ]


async def search_external_indexers(
    session: AsyncSession,
    query: str
) -> List[SearchResultData]:
    results = await gather(*(
        indexer.search(session, query)
        for indexer in ExternalIndexers.get_enabled_indexers()
    ))
    return [
        result
        for indexer_results in results
        for result in indexer_results
    ]
