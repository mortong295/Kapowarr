import unittest

from backend.features.search import _rank_search_result, _score_quality_profile


class quality_profile_search(unittest.TestCase):
    def test_preferred_format_and_custom_formats_score_release(self):
        result = {
            'display_title': 'Batman 001 Digital.cbz',
            'link': 'https://example.invalid/Batman.001.cbz',
            'source': 'GetComics',
            'series': 'Batman',
            'year': 2024,
            'volume_number': 1,
            'special_version': None,
            'issue_number': 1.0,
            'annual': False
        }
        profile = {
            'id': 4,
            'name': 'CBZ Preferred',
            'allowed_formats': ['cbz'],
            'preferred_formats': ['cbz'],
            'custom_formats': {'digital': 50, 'scan': -10}
        }

        quality = _score_quality_profile(result, profile)

        self.assertTrue(quality['quality_profile_match'])
        self.assertIsNone(quality['quality_profile_issue'])
        self.assertEqual(quality['quality_format'], 'cbz')
        self.assertEqual(quality['quality_score'], 150)
        self.assertEqual(quality['quality_rank'], 'Preferred')

    def test_disallowed_format_is_rejected_and_ranked_after_allowed(self):
        profile = {
            'id': 5,
            'name': 'CBZ Only',
            'allowed_formats': ['cbz'],
            'preferred_formats': ['cbz'],
            'custom_formats': {}
        }
        allowed = {
            'display_title': 'Batman 001.cbz',
            'link': 'https://example.invalid/Batman.001.cbz',
            'source': 'GetComics',
            'series': 'Batman',
            'year': 2024,
            'volume_number': 1,
            'special_version': None,
            'issue_number': 1.0,
            'annual': False,
            'match': True,
            'match_issue': None
        }
        rejected = {
            **allowed,
            'display_title': 'Batman 001.pdf',
            'link': 'https://example.invalid/Batman.001.pdf'
        }

        allowed.update(_score_quality_profile(allowed, profile))
        rejected.update(_score_quality_profile(rejected, profile))

        self.assertFalse(rejected['quality_profile_match'])
        self.assertIn('not allowed', rejected['quality_profile_issue'])
        self.assertLess(
            _rank_search_result(allowed, 'Batman', 1),
            _rank_search_result(rejected, 'Batman', 1)
        )


class indexer_search(unittest.IsolatedAsyncioTestCase):
    async def test_raw_rss_indexer_filters_feed_items_by_query(self):
        from backend.features.search import _search_indexer

        class FakeSession:
            async def get_text(self, url, params={}, headers={}, quiet_fail=False):
                self.url = url
                return '''<?xml version="1.0"?>
                    <rss><channel>
                        <item>
                            <title>Batman 001 (2024) (Digital) (Zone).cbz</title>
                            <link>https://example.invalid/batman-001.cbz</link>
                        </item>
                        <item>
                            <title>Superman 001 (2024).cbz</title>
                            <link>https://example.invalid/superman-001.cbz</link>
                        </item>
                    </channel></rss>'''

        results = await _search_indexer(
            FakeSession(),
            'Batman 001',
            {
                'name': 'Weekly RSS',
                'implementation': 'rawrss',
                'settings': {'url': 'https://example.invalid/rss'}
            }
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['source'], 'Weekly RSS')
        self.assertEqual(results[0]['link'], 'https://example.invalid/batman-001.cbz')

    async def test_newznab_indexer_builds_api_search_request(self):
        from backend.features.search import _search_indexer

        class FakeSession:
            async def get_text(self, url, params={}, headers={}, quiet_fail=False):
                self.url = url
                self.params = params
                return '''<?xml version="1.0"?>
                    <rss><channel><item>
                        <title>Batman 002 (2024).cbz</title>
                        <link>https://example.invalid/nzb/1</link>
                    </item></channel></rss>'''

        session = FakeSession()
        results = await _search_indexer(
            session,
            'Batman 002',
            {
                'name': 'Newznab Comics',
                'implementation': 'newznab',
                'settings': {
                    'base_url': 'https://indexer.invalid',
                    'api_key': 'token',
                    'categories': '7030'
                }
            }
        )

        self.assertEqual(session.url, 'https://indexer.invalid/api')
        self.assertEqual(session.params['t'], 'search')
        self.assertEqual(session.params['q'], 'Batman 002')
        self.assertEqual(session.params['apikey'], 'token')
        self.assertEqual(results[0]['source'], 'Newznab Comics')


if __name__ == '__main__':
    unittest.main()
