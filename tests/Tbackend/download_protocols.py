import unittest

from backend.base.definitions import DownloadSource, DownloadType
from backend.features.download_queue import (
    _detect_download_type,
    _normalise_download_source,
    _normalise_download_type
)


class download_protocol_detection(unittest.TestCase):
    def test_explicit_download_type_wins(self):
        self.assertEqual(
            _detect_download_type(
                'https://indexer.invalid/download/1',
                download_type='usenet'
            ),
            'usenet'
        )
        self.assertEqual(
            _detect_download_type(
                'https://indexer.invalid/download/1',
                download_type=DownloadType.TORRENT
            ),
            'torrent'
        )

    def test_common_links_are_detected(self):
        self.assertEqual(
            _detect_download_type('magnet:?xt=urn:btih:abc'),
            'torrent'
        )
        self.assertEqual(
            _detect_download_type('https://indexer.invalid/api?t=get&id=abc'),
            'usenet'
        )
        self.assertEqual(
            _detect_download_type('https://files.invalid/Batman.001.cbz'),
            'direct'
        )
        self.assertIsNone(
            _detect_download_type('https://files.invalid/details/123')
        )

    def test_enum_normalisers_accept_api_values_and_names(self):
        self.assertEqual(_normalise_download_type('newznab'), DownloadType.USENET)
        self.assertEqual(_normalise_download_type(2), DownloadType.TORRENT)
        self.assertEqual(
            _normalise_download_source('Torrent', DownloadSource.DIRECT),
            DownloadSource.TORRENT
        )
        self.assertEqual(
            _normalise_download_source('USENET', DownloadSource.DIRECT),
            DownloadSource.USENET
        )


if __name__ == '__main__':
    unittest.main()
