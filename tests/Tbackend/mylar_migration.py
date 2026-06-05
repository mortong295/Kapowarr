import unittest

from backend.implementations.mylar_import import parse_mylar_export


class mylar_migration_parser(unittest.TestCase):
    def test_parse_mylar_watchlist_pull_list_and_story_arc(self):
        result = parse_mylar_export({
            'comics': [{
                'ComicID': '4050',
                'ComicName': 'Saga',
                'ComicYear': '2012',
                'Publisher': 'Image',
                'ComicLocation': '/comics/Saga (2012)',
                'Status': 'Active'
            }],
            'pull_list': [{
                'ComicName': 'Saga',
                'Issue_Number': '64',
                'IssueName': 'Chapter Sixty Four',
                'IssueDate': '2026-06-17',
                'Publisher': 'Image'
            }],
            'story_arcs': [{
                'StoryName': 'Saga Reading Order',
                'IssueList': [{
                    'ComicName': 'Saga',
                    'Issue_Number': '1',
                    'IssueName': 'Chapter One'
                }]
            }]
        })

        self.assertEqual(result['summary']['volumes'], 1)
        self.assertEqual(result['summary']['pull_list_items'], 1)
        self.assertEqual(result['summary']['story_arcs'], 1)
        self.assertEqual(result['volumes'][0]['comicvine_id'], 4050)
        self.assertEqual(result['volumes'][0]['title'], 'Saga')
        self.assertEqual(result['pull_list'][0]['issue_number'], '64')
        self.assertEqual(result['story_arcs'][0]['issues'][0]['series'], 'Saga')
        self.assertEqual(result['root_folders'], ['/comics/Saga (2012)'])

    def test_parse_json_string_export(self):
        result = parse_mylar_export(
            '{"watchlist":[{"comicvine_id": "123", "title": "Daredevil"}],'
            '"wanted":[{"series": "Daredevil", "number": "1"}]}'
        )

        self.assertEqual(result['volumes'][0]['comicvine_id'], 123)
        self.assertEqual(result['volumes'][0]['title'], 'Daredevil')
        self.assertEqual(result['pull_list'][0]['series'], 'Daredevil')
        self.assertEqual(result['warnings'], [])

    def test_empty_export_reports_warnings(self):
        result = parse_mylar_export({})

        self.assertEqual(result['summary']['volumes'], 0)
        self.assertIn('watchlist', result['warnings'][0])
        self.assertIn('pull-list', result['warnings'][1])


if __name__ == '__main__':
    unittest.main()
