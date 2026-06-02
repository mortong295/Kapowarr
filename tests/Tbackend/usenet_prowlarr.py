import unittest

from backend.implementations.prowlarr import Prowlarr, score_release
from backend.implementations.usenet_clients import SABnzbd


class sabnzbd_mapping(unittest.TestCase):
    def test_queue_response_mapping(self):
        mapped = SABnzbd._map_queue_item({
            'nzo_id': 'SAB-1',
            'filename': 'Batman 001',
            'status': 'Downloading',
            'cat': 'comics',
            'mb': '1 GB',
            'mbleft': '512 MB',
            'percentage': '50',
            'speed': '2 MB/s',
            'timeleft': '00:01:00'
        })
        self.assertEqual(mapped['external_id'], 'SAB-1')
        self.assertEqual(mapped['status'], 'downloading')
        self.assertEqual(mapped['category'], 'comics')
        self.assertEqual(mapped['size'], 1024 ** 3)
        self.assertEqual(mapped['remaining'], 512 * 1024 ** 2)
        self.assertEqual(mapped['percentage'], 50.0)

    def test_numeric_queue_sizes_are_megabytes(self):
        mapped = SABnzbd._map_queue_item({
            'nzo_id': 'SAB-3',
            'filename': 'Batman 003',
            'status': 'Downloading',
            'mb': 512,
            'mbleft': 128,
            'percentage': '75'
        })
        self.assertEqual(mapped['size'], 512 * 1024 ** 2)
        self.assertEqual(mapped['remaining'], 128 * 1024 ** 2)

    def test_delete_download_uses_queue_for_active_download(self):
        calls = []
        client = SABnzbd.__new__(SABnzbd)
        client._base_url = 'http://sabnzbd.invalid'
        client._api_token = 'token'
        client.get_queue = lambda: [{'external_id': 'SAB-4'}]
        client._settings = lambda: {'timeout': 30, 'verify': True}

        def fake_request(base_url, api_token, mode, params, **kwargs):
            calls.append((mode, params))
            return {}

        original_request = SABnzbd._request
        try:
            SABnzbd._request = staticmethod(fake_request)
            client.delete_download('SAB-4', True)
        finally:
            SABnzbd._request = original_request

        self.assertEqual(calls[0][0], 'queue')
        self.assertEqual(calls[0][1]['del_files'], 1)

    def test_delete_download_uses_history_for_completed_download(self):
        calls = []
        client = SABnzbd.__new__(SABnzbd)
        client._base_url = 'http://sabnzbd.invalid'
        client._api_token = 'token'
        client.get_queue = lambda: []
        client._settings = lambda: {'timeout': 30, 'verify': True}

        def fake_request(base_url, api_token, mode, params, **kwargs):
            calls.append((mode, params))
            return {}

        original_request = SABnzbd._request
        try:
            SABnzbd._request = staticmethod(fake_request)
            client.delete_download('SAB-5', False)
        finally:
            SABnzbd._request = original_request

        self.assertEqual(calls[0][0], 'history')
        self.assertEqual(calls[0][1]['del_files'], 0)

    def test_history_response_mapping(self):
        mapped = SABnzbd._map_history_item({
            'nzo_id': 'SAB-2',
            'name': 'Batman 001',
            'status': 'Completed',
            'category': 'comics',
            'storage': '/downloads/comics/Batman 001',
            'download_time': 123
        })
        self.assertEqual(mapped['external_id'], 'SAB-2')
        self.assertEqual(mapped['status'], 'importing')
        self.assertEqual(mapped['completed_path'], '/downloads/comics/Batman 001')
        self.assertEqual(mapped['download_time'], 123)


class prowlarr_mapping(unittest.TestCase):
    def test_filters_torrent_result(self):
        self.assertIsNone(Prowlarr._map_result({
            'title': 'Batman 001',
            'downloadUrl': 'https://example.invalid/torrent',
            'protocol': 'torrent'
        }))

    def test_maps_usenet_result(self):
        mapped = Prowlarr._map_result({
            'title': 'Batman 001 (2016)',
            'downloadUrl': 'https://example.invalid/getnzb/1',
            'guid': 'guid-1',
            'protocol': 'usenet',
            'indexer': 'Example Indexer',
            'size': 1234
        })
        self.assertIsNotNone(mapped)
        self.assertEqual(mapped['link'], 'https://example.invalid/getnzb/1')
        self.assertEqual(mapped['source'], 'Prowlarr')
        self.assertEqual(mapped['download_type'], 'usenet')
        self.assertEqual(mapped['indexer'], 'Example Indexer')
        self.assertEqual(mapped['size'], 1234)


class release_scoring(unittest.TestCase):
    def test_exact_issue_match(self):
        result = {
            'display_title': 'Batman 001 (2016) (Digital)',
            'issue_number': 1.0,
            'year': 2016,
            'special_version': None
        }
        score, reasons = score_release(result, 'Batman', 1.0, 2016)
        self.assertGreaterEqual(score, 85)
        self.assertIn('series title match', reasons)
        self.assertIn('issue number match', reasons)
        self.assertIn('year match', reasons)

    def test_and_ampersand_normalisation(self):
        result = {
            'display_title': 'Batman and Robin 001 (2011)',
            'issue_number': 1.0,
            'year': 2011
        }
        score, _ = score_release(result, 'Batman & Robin', 1.0, 2011)
        self.assertGreaterEqual(score, 85)

    def test_wrong_issue_downscored(self):
        result = {
            'display_title': 'Batman 002 (2016)',
            'issue_number': 2.0,
            'year': 2016
        }
        score, _ = score_release(result, 'Batman', 1.0, 2016)
        self.assertLess(score, 90)
