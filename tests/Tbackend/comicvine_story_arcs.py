import unittest

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


if __name__ == '__main__':
    unittest.main()
