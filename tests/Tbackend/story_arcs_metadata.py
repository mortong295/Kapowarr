import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Flask

from backend.features import tasks
from backend.features.tasks import WriteAllMetadata, WriteVolumeMetadata
from backend.implementations.arr_features import (get_story_arc,
                                                  save_story_arc,
                                                  write_volume_metadata)
from backend.internals.db import close_db, get_db, set_db_location, setup_db
from backend.internals.server import Server


class story_arcs_and_metadata(unittest.TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        self.root = Path(self.tempdir.name) / 'library'
        self.volume_folder = self.root / 'Batman (2026)'
        self.volume_folder.mkdir(parents=True)
        set_db_location(str(Path(self.tempdir.name) / 'db'))
        Server.url_base = ''
        self.app = Flask(__name__)
        self.ctx = self.app.app_context()
        self.ctx.push()
        setup_db()
        cursor = get_db()
        cursor.execute(
            "INSERT INTO root_folders(id, folder) VALUES(?, ?);",
            (1, str(self.root))
        )
        cursor.execute(
            """
            INSERT INTO volumes(
                id, comicvine_id, title, alt_title, year, publisher,
                volume_number, description, site_url, monitored,
                quality_profile_id, root_folder, folder, special_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                1, 100, 'Batman', 'Batman', 2026, 'DC Comics', 1,
                'Batman volume description', 'https://comicvine.invalid/100',
                True, 1, 1, str(self.volume_folder), None
            )
        )
        cursor.execute(
            """
            INSERT INTO issues(
                id, volume_id, comicvine_id, issue_number,
                calculated_issue_number, title, date, description, monitored
            ) VALUES (?,?,?,?,?,?,?,?,?);
            """,
            (
                1, 1, 101, '1', 1.0, 'Court of Owls', '2026-06-10',
                'Issue description', True
            )
        )

    def tearDown(self):
        close_db()
        self.ctx.pop()
        self.tempdir.cleanup()

    def test_story_arc_issue_matches_volume_and_issue_by_series(self):
        arc = save_story_arc({
            'title': 'Court of Owls',
            'issues': [{
                'series': 'Batman',
                'issue_number': '1'
            }]
        })
        stored = get_story_arc(arc['id'])

        self.assertEqual(stored['issues'][0]['volume_id'], 1)
        self.assertEqual(stored['issues'][0]['issue_id'], 1)
        self.assertEqual(stored['issues'][0]['matched_issue_number'], '1')

    def test_write_metadata_task_outputs_comicinfo_and_series_json(self):
        class FakeWebSocket:
            def emit(self, event):
                return None

        original_websocket = tasks.WebSocket
        tasks.WebSocket = FakeWebSocket
        try:
            WriteVolumeMetadata(1).run()
        finally:
            tasks.WebSocket = original_websocket

        self.assertTrue((self.volume_folder / 'ComicInfo.xml').exists())
        self.assertTrue((self.volume_folder / 'series.json').exists())

    def test_write_all_metadata_task_outputs_comicinfo_and_series_json(self):
        class FakeWebSocket:
            def emit(self, event):
                return None

        original_websocket = tasks.WebSocket
        tasks.WebSocket = FakeWebSocket
        try:
            WriteAllMetadata().run()
        finally:
            tasks.WebSocket = original_websocket

        self.assertTrue((self.volume_folder / 'ComicInfo.xml').exists())
        self.assertTrue((self.volume_folder / 'series.json').exists())

    def test_write_volume_metadata_outputs_comicinfo_and_series_json(self):
        result = write_volume_metadata(1)
        files = {item['type']: item for item in result['files']}

        self.assertIn('comicinfo', files)
        self.assertIn('series_json', files)
        self.assertTrue((self.volume_folder / 'ComicInfo.xml').exists())
        series_path = self.volume_folder / 'series.json'
        self.assertTrue(series_path.exists())
        series = json.loads(series_path.read_text())
        self.assertEqual(series['title'], 'Batman')
        self.assertEqual(series['issues'][0]['issue_number'], '1')


if __name__ == '__main__':
    unittest.main()
