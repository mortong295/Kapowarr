import unittest

from backend.implementations import mylar_import
from backend.implementations.mylar_import import (apply_mylar_export,
                                                  parse_mylar_export)


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

    def test_apply_mylar_export_adds_volumes_pull_list_and_story_arcs(self):
        added = []
        pull_items = []
        arcs = []
        original_library = mylar_import.Library
        original_default = mylar_import.get_default_profile_id
        original_pull = mylar_import.save_pull_list_item
        original_arc = mylar_import.save_story_arc

        class FakeLibrary:
            @staticmethod
            def add(*args):
                added.append(args)
                return 99

        try:
            mylar_import.Library = FakeLibrary
            mylar_import.get_default_profile_id = lambda: 1
            mylar_import.save_pull_list_item = lambda item: pull_items.append(item) or item
            mylar_import.save_story_arc = lambda arc: arcs.append(arc) or arc

            result = apply_mylar_export({
                'watchlist': [{
                    'comicvine_id': 123,
                    'title': 'Daredevil'
                }],
                'wanted': [{
                    'series': 'Daredevil',
                    'number': '1'
                }],
                'story_arcs': [{
                    'name': 'Born Again',
                    'issues': [{'series': 'Daredevil', 'number': '227'}]
                }]
            }, {
                'root_folder_id': 2,
                'quality_profile_id': 3,
                'provider': 'Mylar'
            })
        finally:
            mylar_import.Library = original_library
            mylar_import.get_default_profile_id = original_default
            mylar_import.save_pull_list_item = original_pull
            mylar_import.save_story_arc = original_arc

        self.assertEqual(result['summary']['volumes_added'], 1)
        self.assertEqual(result['summary']['pull_list_items'], 1)
        self.assertEqual(result['summary']['story_arcs'], 1)
        self.assertEqual(added[0][0], 123)
        self.assertEqual(added[0][1], 2)
        self.assertEqual(added[0][-1], 3)
        self.assertEqual(pull_items[0]['provider'], 'Mylar')
        self.assertEqual(arcs[0]['title'], 'Born Again')


if __name__ == '__main__':
    unittest.main()
