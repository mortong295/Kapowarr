import unittest
from tempfile import TemporaryDirectory

from flask import Flask

from backend.features import tasks
from backend.features.tasks import (SearchStoryArcMissing,
                                    SearchWantedCutoffUnmet,
                                    SearchWantedMissing)
from backend.implementations.arr_features import count_cutoff_unmet_issues
from backend.internals.db import close_db, get_db, set_db_location, setup_db
from backend.internals.server import Server
from frontend import api as api_module


class wanted_search_tasks(unittest.TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        set_db_location(self.tempdir.name)
        Server.url_base = ''
        self.app = Flask(__name__)
        self.ctx = self.app.app_context()
        self.ctx.push()
        setup_db()
        cursor = get_db()
        cursor.execute("INSERT INTO root_folders(id, folder) VALUES(?, ?);", (1, '/tmp/library'))
        cursor.execute(
            """
            INSERT INTO volumes(
                id, comicvine_id, title, alt_title, year, monitored,
                quality_profile_id, root_folder, folder, special_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?);
            """,
            (1, 100, 'Batman', 'Batman', 2026, True, 1, 1, '/tmp/library/Batman', None)
        )
        cursor.execute(
            """
            INSERT INTO issues(
                id, volume_id, comicvine_id, issue_number,
                calculated_issue_number, title, monitored
            ) VALUES (?,?,?,?,?,?,?);
            """,
            (1, 1, 101, '1', 1.0, 'One', True)
        )
        self.calls = []

        class FakeWebSocket:
            def emit(self, event):
                return None

        def fake_auto_search(volume_id, issue_id=None):
            self.calls.append((volume_id, issue_id))
            return [{
                'link': f'https://example.invalid/{volume_id}/{issue_id}',
                'match': True,
                'quality_profile_match': True
            }]

        self.original_websocket = tasks.WebSocket
        self.original_auto_search = tasks.auto_search
        tasks.WebSocket = FakeWebSocket
        tasks.auto_search = fake_auto_search

    def tearDown(self):
        tasks.WebSocket = self.original_websocket
        tasks.auto_search = self.original_auto_search
        close_db()
        self.ctx.pop()
        self.tempdir.cleanup()

    def test_search_wanted_missing_returns_downloads_for_missing_issues(self):
        result = SearchWantedMissing().run()

        self.assertEqual(self.calls, [(1, 1)])
        self.assertEqual(
            result,
            [('https://example.invalid/1/1', 1, 1, False, {})]
        )

    def test_missing_issue_count_matches_paginated_items(self):
        self.assertEqual(api_module._missing_issue_count(), 1)
        self.assertEqual(
            len(api_module._missing_issues(limit=1, offset=0)),
            1
        )
        self.assertEqual(
            len(api_module._missing_issues(limit=1, offset=1)),
            0
        )

    def test_search_wanted_cutoff_unmet_returns_downloads_for_upgradeable_issue(self):
        cursor = get_db()
        cursor.execute(
            "INSERT INTO files(id, filepath, size) VALUES(?,?,?);",
            (1, '/tmp/library/Batman/Batman 001.pdf', 100)
        )
        cursor.execute(
            "INSERT INTO issues_files(file_id, issue_id) VALUES(?, ?);",
            (1, 1)
        )

        result = SearchWantedCutoffUnmet().run()

        self.assertEqual(self.calls, [(1, 1)])
        self.assertEqual(
            result,
            [('https://example.invalid/1/1', 1, 1, False, {})]
        )

    def test_cutoff_unmet_count_matches_quality_decision(self):
        cursor = get_db()
        cursor.execute(
            "INSERT INTO files(id, filepath, size) VALUES(?,?,?);",
            (1, '/tmp/library/Batman/Batman 001.pdf', 100)
        )
        cursor.execute(
            "INSERT INTO issues_files(file_id, issue_id) VALUES(?, ?);",
            (1, 1)
        )

        self.assertEqual(count_cutoff_unmet_issues(), 1)

    def test_search_story_arc_missing_deduplicates_matched_issues(self):
        cursor = get_db()
        cursor.execute(
            "INSERT INTO story_arcs(id, title, monitored, created_at, updated_at) VALUES(?,?,?,?,?);",
            (1, 'Court of Owls', True, 1, 1)
        )
        cursor.execute(
            """
            INSERT INTO story_arc_issues(
                story_arc_id, reading_order, volume_id, issue_id, title, monitored
            ) VALUES (?,?,?,?,?,?);
            """,
            (1, 1, 1, 1, 'One', True)
        )
        cursor.execute(
            """
            INSERT INTO story_arc_issues(
                story_arc_id, reading_order, volume_id, issue_id, title, monitored
            ) VALUES (?,?,?,?,?,?);
            """,
            (1, 2, 1, 1, 'One Duplicate', True)
        )

        result = SearchStoryArcMissing().run()

        self.assertEqual(self.calls, [(1, 1)])
        self.assertEqual(
            result,
            [('https://example.invalid/1/1', 1, 1, False, {})]
        )


if __name__ == '__main__':
    unittest.main()
