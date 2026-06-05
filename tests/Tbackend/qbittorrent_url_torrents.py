import unittest
from types import SimpleNamespace

from backend.base.definitions import Constants, DownloadState
from backend.implementations.torrent_clients.qBittorrent import qBittorrent


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, torrent_pages=None, tagged_torrents=None):
        self.torrent_pages = list(torrent_pages or [])
        self.tagged_torrents = tagged_torrents or []
        self.posts = []
        self.gets = []

    def get(self, url, params=None):
        params = params or {}
        self.gets.append({'url': url, 'params': params})
        if params.get('tag'):
            return FakeResponse(self.tagged_torrents)
        if self.torrent_pages:
            return FakeResponse(self.torrent_pages.pop(0))
        return FakeResponse([])

    def post(self, url, files=None, data=None):
        self.posts.append({'url': url, 'files': files, 'data': data})
        return FakeResponse({})


def make_client(session):
    client = qBittorrent.__new__(qBittorrent)
    client._id = 1
    client._title = 'qBittorrent'
    client._base_url = 'http://qbittorrent.invalid'
    client._username = None
    client._password = None
    client._api_token = None
    client.ssn = session
    client.torrent_hashes = {}
    client.settings = SimpleNamespace(
        sv=SimpleNamespace(failing_download_timeout=0)
    )
    return client


class qbittorrent_url_torrents(unittest.TestCase):
    def test_url_torrent_uses_new_hash_when_qbittorrent_reports_it(self):
        session = FakeSession([
            [],
            [{'hash': 'abc123'}]
        ])
        client = make_client(session)

        download_id = client.add_download(
            'https://indexer.invalid/download/123.torrent',
            '/downloads',
            None
        )

        self.assertEqual(download_id, 'abc123')
        files = session.posts[0]['files']
        self.assertEqual(files['urls'][1], 'https://indexer.invalid/download/123.torrent')
        self.assertEqual(files['category'][1], Constants.TORRENT_TAG)
        self.assertTrue(files['tags'][1].startswith(f'{Constants.TORRENT_TAG}-'))

    def test_url_torrent_falls_back_to_tag_tracking_until_hash_is_visible(self):
        tagged_torrents = [{
            'hash': 'def456',
            'state': 'downloading',
            'total_size': 100,
            'progress': 0.25,
            'dlspeed': 2048
        }]
        session = FakeSession([[], []], tagged_torrents)
        client = make_client(session)

        download_id = client.add_download(
            'https://indexer.invalid/download/456',
            '/downloads',
            'Batman 001'
        )
        status = client.get_download(download_id)

        self.assertTrue(download_id.startswith(f'tag:{Constants.TORRENT_TAG}-'))
        self.assertEqual(status['state'], DownloadState.DOWNLOADING_STATE)
        self.assertEqual(status['progress'], 25.0)
        self.assertEqual(session.gets[-1]['params']['tag'], download_id[4:])

    def test_tag_tracked_url_torrent_deletes_resolved_hash(self):
        session = FakeSession(tagged_torrents=[{'hash': 'def456'}])
        client = make_client(session)
        client.torrent_hashes['tag:kapowarr-test'] = None

        client.delete_download('tag:kapowarr-test', True)

        self.assertEqual(
            session.posts[0]['data'],
            {'hashes': 'def456', 'deleteFiles': True}
        )
        self.assertNotIn('tag:kapowarr-test', client.torrent_hashes)


if __name__ == '__main__':
    unittest.main()
