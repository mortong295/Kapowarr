import unittest
from types import SimpleNamespace

from backend.features import download_queue, post_processing, search


class failed_download_replacement(unittest.TestCase):
    def setUp(self):
        self.original_auto_search = search.auto_search
        self.original_download_handler = download_queue.DownloadHandler

    def tearDown(self):
        search.auto_search = self.original_auto_search
        download_queue.DownloadHandler = self.original_download_handler

    def test_replacement_skips_failed_link_and_queues_next_result(self):
        queued = []

        def fake_auto_search(volume_id, issue_id=None):
            return [
                {
                    'link': 'https://failed.invalid/release',
                    'display_title': 'Failed Release'
                },
                {
                    'link': 'https://indexer.invalid/api?t=get&id=2',
                    'display_title': 'Replacement Release',
                    'download_type': 'usenet',
                    'source_type': 'Usenet',
                    'source': 'NZBgeek'
                }
            ]

        class FakeDownloadHandler:
            def add_multiple(self, args):
                queued.extend(args)

        search.auto_search = fake_auto_search
        download_queue.DownloadHandler = FakeDownloadHandler

        post_processing.queue_replacement_download(SimpleNamespace(
            id=7,
            volume_id=1,
            issue_id=2,
            web_link='https://failed.invalid/release',
            download_link='https://failed.invalid/release'
        ))

        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0][0], 'https://indexer.invalid/api?t=get&id=2')
        self.assertEqual(queued[0][4]['download_type'], 'usenet')
        self.assertEqual(queued[0][4]['source_name'], 'NZBgeek')


if __name__ == '__main__':
    unittest.main()
