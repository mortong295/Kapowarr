import unittest

from backend.base.custom_exceptions import CredentialInvalid
from backend.implementations import external_indexers
from backend.implementations.external_indexers import (ExternalIndexers,
                                                       NewznabIndexer,
                                                       ProwlarrIndexer)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.payload = payload
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, response, calls):
        self.response = response
        self.calls = calls

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class indexer_clients(unittest.TestCase):
    def test_prowlarr_connection_uses_api_key_header(self):
        calls = []
        original_session = external_indexers.Session
        try:
            external_indexers.Session = lambda: FakeSession(
                FakeResponse(payload={'version': '1.0.0'}),
                calls
            )
            ProwlarrIndexer.test('http://prowlarr:9696', 'secret')
        finally:
            external_indexers.Session = original_session

        self.assertEqual(
            calls[0][0],
            'http://prowlarr:9696/api/v1/system/status'
        )
        self.assertEqual(calls[0][1]['headers']['X-Api-Key'], 'secret')

    def test_newznab_caps_accepts_xml_response(self):
        calls = []
        original_session = external_indexers.Session
        try:
            external_indexers.Session = lambda: FakeSession(
                FakeResponse(text='<caps></caps>'),
                calls
            )
            NewznabIndexer.test('https://indexer.example/api', 'secret')
        finally:
            external_indexers.Session = original_session

        self.assertEqual(calls[0][0], 'https://indexer.example/api')
        self.assertEqual(calls[0][1]['params']['t'], 'caps')
        self.assertEqual(calls[0][1]['params']['apikey'], 'secret')

    def test_newznab_auth_failure_is_credential_invalid(self):
        calls = []
        original_session = external_indexers.Session
        try:
            external_indexers.Session = lambda: FakeSession(
                FakeResponse(status_code=403),
                calls
            )
            with self.assertRaises(CredentialInvalid):
                NewznabIndexer.test('https://indexer.example', 'bad')
        finally:
            external_indexers.Session = original_session

    def test_categories_are_normalised_for_storage(self):
        self.assertEqual(
            ExternalIndexers.normalise_categories('7030, 8020\n8030'),
            '7030,8020,8030'
        )
        self.assertIsNone(ExternalIndexers.normalise_categories(''))

    def test_masked_api_key_is_preserved_on_update(self):
        data = ExternalIndexers.prepare_data(
            'Prowlarr',
            {
                'title': 'Prowlarr',
                'base_url': 'http://prowlarr:9696',
                'api_key': '********',
                'enabled': True,
                'categories': ['7030']
            },
            existing_api_key='secret'
        )

        self.assertEqual(data['api_key'], 'secret')
        self.assertEqual(data['categories'], '7030')

    def test_prowlarr_search_mapping_filters_torrents(self):
        mapped = ProwlarrIndexer._format_results([
            {
                'title': 'Batman 001 (2026)',
                'downloadUrl': 'http://prowlarr/download/1',
                'indexer': 'NZBFinder',
                'protocol': 'usenet'
            },
            {
                'title': 'Batman 002 (2026)',
                'downloadUrl': 'magnet:?xt=urn:btih:abc',
                'indexer': 'Torrent Indexer',
                'protocol': 'torrent'
            }
        ], 'Prowlarr')

        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]['link'], 'http://prowlarr/download/1')
        self.assertEqual(mapped[0]['source'], 'NZBFinder')
        self.assertEqual(mapped[0]['issue_number'], 1.0)

    def test_newznab_search_mapping_uses_release_link(self):
        mapped = NewznabIndexer._format_results(
            '{"channel":{"item":[{"title":"Batman 001 (2026)",'
            '"link":"https://indexer/api?t=get&id=abc"}]}}',
            'NZBgeek'
        )

        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]['link'], 'https://indexer/api?t=get&id=abc')
        self.assertEqual(mapped[0]['source'], 'NZBgeek')
        self.assertEqual(mapped[0]['issue_number'], 1.0)
