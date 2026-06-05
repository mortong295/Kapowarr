import unittest
from os import environ
from types import SimpleNamespace

from backend.implementations import comicvine
from backend.implementations.comicvine import ComicVine


class comicvine_story_arc_formatting(unittest.TestCase):
    def test_story_arc_result_formats_issue_payloads(self):
        cv = ComicVine.__new__(ComicVine)

        result = cv._format_story_arc_output({
            'id': 4045,
            'name': 'Court of Owls',
            'description': '<p>Batman reading order.</p>',
            'site_detail_url': 'https://comicvine.invalid/story/4045',
            'issues': [{
                'id': 4000,
                'issue_number': '1',
                'name': 'Knife Trick',
                'volume': {'name': 'Batman'}
            }]
        })

        self.assertEqual(result['comicvine_id'], 4045)
        self.assertEqual(result['title'], 'Court of Owls')
        self.assertEqual(result['issues'][0]['series'], 'Batman')
        self.assertEqual(result['issues'][0]['issue_number'], '1')
        self.assertEqual(result['issues'][0]['comicvine_issue_id'], 4000)

    def test_story_arc_issue_details_fill_sparse_issue_refs(self):
        cv = ComicVine.__new__(ComicVine)

        result = cv._format_story_arc_output(
            {
                'id': 4046,
                'name': 'Sparse Arc',
                'issues': [{
                    'id': 4001,
                    'name': 'Sparse Ref'
                }]
            },
            {
                4001: {
                    'id': 4001,
                    'issue_number': '2',
                    'name': 'Full Issue',
                    'volume': {'name': 'Batman'}
                }
            }
        )

        self.assertEqual(result['issues'][0]['series'], 'Batman')
        self.assertEqual(result['issues'][0]['issue_number'], '2')
        self.assertEqual(result['issues'][0]['title'], 'Full Issue')

    def test_comicvine_uses_environment_api_key_when_setting_is_empty(self):
        original_settings = comicvine.Settings
        original_session = comicvine.Session
        original_env = environ.get('COMICVINE_API_KEY')
        try:
            comicvine.Settings = lambda: SimpleNamespace(
                get_settings=lambda: SimpleNamespace(
                    date_type=SimpleNamespace(value='cover_date'),
                    comicvine_api_key=''
                )
            )
            comicvine.Session = lambda: SimpleNamespace(params={})
            environ['COMICVINE_API_KEY'] = 'env-comicvine-key'

            cv = ComicVine()

            self.assertEqual(cv._params['api_key'], 'env-comicvine-key')
        finally:
            comicvine.Settings = original_settings
            comicvine.Session = original_session
            if original_env is None:
                environ.pop('COMICVINE_API_KEY', None)
            else:
                environ['COMICVINE_API_KEY'] = original_env


if __name__ == '__main__':
    unittest.main()
