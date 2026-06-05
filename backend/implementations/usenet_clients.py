# -*- coding: utf-8 -*-

from os.path import basename
from typing import Any, Dict, List, Mapping, Union

from requests.exceptions import RequestException

from backend.base.custom_exceptions import ClientNotWorking, CredentialInvalid
from backend.base.definitions import BrokenClientReason, DownloadState, DownloadType
from backend.base.helpers import Session
from backend.base.logging import LOGGER
from backend.implementations.external_clients import BaseExternalClient
from backend.internals.settings import Settings


class SABnzbd(BaseExternalClient):
    """SABnzbd download client implementation using the public HTTP API."""

    client_type = 'SABnzbd'
    download_type = DownloadType.USENET

    required_tokens = ('title', 'base_url', 'api_token')

    status_mapping = {
        'queued': DownloadState.QUEUED_STATE,
        'paused': DownloadState.PAUSED_STATE,
        'downloading': DownloadState.DOWNLOADING_STATE,
        'running': DownloadState.DOWNLOADING_STATE,
        'fetching': DownloadState.DOWNLOADING_STATE,
        'checking': DownloadState.DOWNLOADING_STATE,
        'verifying': DownloadState.DOWNLOADING_STATE,
        'repairing': DownloadState.DOWNLOADING_STATE,
        'extracting': DownloadState.DOWNLOADING_STATE,
        'unpacking': DownloadState.DOWNLOADING_STATE,
        'moving': DownloadState.DOWNLOADING_STATE,
        'completed': DownloadState.IMPORTING_STATE,
        'complete': DownloadState.IMPORTING_STATE,
        'failed': DownloadState.FAILED_STATE
    }

    priority_mapping = {
        'default': -100,
        'paused': -2,
        'low': -1,
        'normal': 0,
        'high': 1,
        'force': 2
    }

    def __init__(self, client_id: int) -> None:
        super().__init__(client_id)
        self.settings = Settings()
        return

    @classmethod
    def _request(
        cls,
        base_url: str,
        api_token: Union[str, None],
        mode: str,
        params: Union[Mapping[str, Any], None] = None,
        files: Union[Mapping[str, Any], None] = None,
        timeout: Union[int, None] = None,
        verify: bool = True
    ) -> Dict[str, Any]:
        ssn = Session()
        data: Dict[str, Any] = {
            'mode': mode,
            'output': 'json'
        }
        if api_token:
            data['apikey'] = api_token
        if params:
            data.update(params)

        try:
            if files:
                response = ssn.post(
                    f'{base_url}/api',
                    data=data,
                    files=files,
                    timeout=timeout,
                    verify=verify
                )
            else:
                response = ssn.get(
                    f'{base_url}/api',
                    params=data,
                    timeout=timeout,
                    verify=verify
                )

        except RequestException:
            LOGGER.exception("Can't connect to SABnzbd instance: ")
            raise ClientNotWorking(BrokenClientReason.CONNECTION_ERROR)

        if response.status_code in (401, 403):
            raise CredentialInvalid

        try:
            result = response.json()
        except ValueError:
            LOGGER.error('Unexpected SABnzbd response: %s', response.text[:500])
            raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

        if isinstance(result, dict) and result.get('error'):
            error = str(result.get('error'))
            if 'api key' in error.lower() or 'apikey' in error.lower():
                raise CredentialInvalid
            LOGGER.error('SABnzbd returned an error: %s', error)
            raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

        if not response.ok:
            raise ClientNotWorking(BrokenClientReason.NOT_CLIENT_INSTANCE)

        if not isinstance(result, dict):
            raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

        return result

    @classmethod
    def test(
        cls,
        base_url: str,
        username: Union[str, None],
        password: Union[str, None],
        api_token: Union[str, None]
    ) -> None:
        cls._request(base_url, api_token, 'version')
        return

    def _settings(self) -> Dict[str, Any]:
        return {
            'timeout': self.settings.sv.sabnzbd_timeout_seconds,
            'verify': self.settings.sv.sabnzbd_use_ssl_verify
        }

    def add_download(
        self,
        download_link: str,
        target_folder: str,
        download_name: Union[str, None]
    ) -> str:
        settings = self._settings()
        result = self._request(
            self.base_url,
            self.api_token,
            'addurl',
            {
                'name': download_link,
                'nzbname': download_name or basename(download_link),
                'cat': self.settings.sv.sabnzbd_category,
                'priority': self.priority_mapping.get(
                    self.settings.sv.sabnzbd_priority,
                    0
                )
            },
            **settings
        )
        nzo_ids = result.get('nzo_ids') or []
        if nzo_ids:
            return str(nzo_ids[0])
        if result.get('status') is True:
            return str(result.get('nzo_id') or download_name or download_link)
        raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

    def add_nzb_file(
        self,
        filename: str,
        content: bytes,
        download_name: Union[str, None] = None
    ) -> str:
        settings = self._settings()
        result = self._request(
            self.base_url,
            self.api_token,
            'addfile',
            {
                'nzbname': download_name or filename,
                'cat': self.settings.sv.sabnzbd_category,
                'priority': self.priority_mapping.get(
                    self.settings.sv.sabnzbd_priority,
                    0
                )
            },
            files={'nzbfile': (filename, content)},
            **settings
        )
        nzo_ids = result.get('nzo_ids') or []
        if nzo_ids:
            return str(nzo_ids[0])
        if result.get('status') is True:
            return str(result.get('nzo_id') or filename)
        raise ClientNotWorking(BrokenClientReason.FAILED_PROCESSING_RESPONSE)

    @staticmethod
    def _size_to_int(value: Any, default_unit: str = 'B') -> int:
        if isinstance(value, (int, float)):
            return int(value * SABnzbd._unit_multiplier(default_unit))
        if not isinstance(value, str):
            return 0
        parts = value.strip().split()
        try:
            number = float(parts[0])
        except (IndexError, ValueError):
            return 0
        unit = parts[1].upper() if len(parts) > 1 else default_unit
        return int(number * SABnzbd._unit_multiplier(unit))

    @staticmethod
    def _unit_multiplier(unit: str) -> int:
        mult = {
            'B': 1, 'KB': 1024, 'MB': 1024**2,
            'GB': 1024**3, 'TB': 1024**4
        }
        return mult.get(unit.upper(), 1)

    def get_queue(self) -> List[Dict[str, Any]]:
        result = self._request(
            self.base_url, self.api_token,
            'queue', **self._settings()
        )
        slots = result.get('queue', {}).get('slots', [])
        return [self._map_queue_item(item) for item in slots]

    @classmethod
    def _map_queue_item(cls, item: Mapping[str, Any]) -> Dict[str, Any]:
        percentage = item.get('percentage', item.get('mbleft', 0))
        try:
            percentage = float(percentage)
        except (TypeError, ValueError):
            percentage = 0.0
        status = str(item.get('status', '')).lower()
        return {
            'external_id': str(item.get('nzo_id') or item.get('id') or ''),
            'name': item.get('filename') or item.get('name') or '',
            'status': cls.status_mapping.get(
                status,
                DownloadState.DOWNLOADING_STATE
            ).value,
            'category': item.get('cat') or item.get('category') or '',
            'size': cls._size_to_int(item.get('mb') or item.get('size'), 'MB'),
            'remaining': cls._size_to_int(
                item.get('mbleft')
                or item.get('remaining'),
                'MB'
            ),
            'percentage': percentage,
            'speed': item.get('speed') or '',
            'estimated_time_remaining': (
                item.get('timeleft')
                or item.get('eta')
                or ''
            )
        }

    def get_history(
        self,
        external_id: Union[str, None] = None
    ) -> List[Dict[str, Any]]:
        result = self._request(
            self.base_url, self.api_token,
            'history', **self._settings()
        )
        slots = result.get('history', {}).get('slots', [])
        mapped = [self._map_history_item(item) for item in slots]
        if external_id is not None:
            mapped = [
                item
                for item in mapped
                if item['external_id'] == external_id
            ]
        return mapped

    @classmethod
    def _map_history_item(cls, item: Mapping[str, Any]) -> Dict[str, Any]:
        status = str(item.get('status', '')).lower()
        return {
            'external_id': str(item.get('nzo_id') or item.get('id') or ''),
            'name': item.get('name') or item.get('filename') or '',
            'status': cls.status_mapping.get(
                status,
                DownloadState.FAILED_STATE
            ).value,
            'category': item.get('category') or item.get('cat') or '',
            'completed_path': (
                item.get('storage')
                or item.get('download_path')
                or ''
            ),
            'failure_message': (
                item.get('fail_message')
                or item.get('script_log')
                or ''
            ),
            'download_time': item.get('download_time') or 0,
            'post_processing_result': (
                item.get('action_line')
                or item.get('stage_log')
                or ''
            )
        }

    def get_download(self, download_id: str) -> Union[Dict[str, Any], None]:
        for item in self.get_queue():
            if item['external_id'] == download_id:
                return {
                    'size': item['size'],
                    'progress': item['percentage'],
                    'speed': item['speed'],
                    'state': DownloadState(item['status'])
                }
        for item in self.get_history(download_id):
            local_path = item.get('completed_path') or ''
            if not local_path and self.settings.sv.sabnzbd_completed_download_root:
                local_path = (
                    self.settings.sv.sabnzbd_completed_download_root.rstrip('/')
                    + '/'
                    + item.get('name', '')
                )
            state = DownloadState(item['status'])
            if state == DownloadState.IMPORTING_STATE:
                state = DownloadState.IMPORTING_STATE
            return {
                'size': 0,
                'progress': (
                    100.0
                    if state == DownloadState.IMPORTING_STATE else
                    0.0
                ),
                'speed': 0,
                'state': state,
                'files': [local_path] if local_path else []
            }
        return {}

    def delete_download(self, download_id: str, delete_files: bool) -> None:
        mode = 'history'
        try:
            if any(
                item['external_id'] == download_id
                for item in self.get_queue()
            ):
                mode = 'queue'
        except ClientNotWorking:
            # Fall back to history deletion for completed downloads if the queue
            # cannot be inspected; the caller is already handling client errors.
            mode = 'history'

        self._request(
            self.base_url,
            self.api_token,
            mode,
            {
                'name': 'delete',
                'value': download_id,
                'del_files': int(delete_files)
            },
            **self._settings()
        )
        return
