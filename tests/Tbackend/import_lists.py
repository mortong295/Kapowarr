import unittest
from tempfile import TemporaryDirectory
from time import gmtime, strftime, time

from flask import Flask

from backend.implementations.arr_features import (delete_pull_list_item,
                                                  get_calendar_pull_list,
                                                  get_pull_list, save_provider,
                                                  save_pull_list_item,
                                                  sync_enabled_import_lists,
                                                  sync_import_list)
from backend.internals.db import close_db, get_db, set_db_location, setup_db
from backend.internals.server import Server


def _date_from_now(days: int) -> str:
    return strftime('%Y-%m-%d', gmtime(time() + days * 86400))


class import_list_sync(unittest.TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        set_db_location(self.tempdir.name)
        Server.url_base = ''
        self.app = Flask(__name__)
        self.ctx = self.app.app_context()
        self.ctx.push()
        setup_db()

    def tearDown(self):
        close_db()
        self.ctx.pop()
        self.tempdir.cleanup()

    def test_json_items_sync_to_pull_list(self):
        provider = save_provider('importlists', {
            'name': 'Weekly JSON',
            'implementation': 'json',
            'enabled': True,
            'settings': {
                'items': [{
                    'release_date': _date_from_now(7),
                    'publisher': 'DC Comics',
                    'series': 'Batman',
                    'issue_number': '1',
                    'issue_title': 'A New Beginning'
                }]
            }
        })

        result = sync_import_list(provider['id'])
        items = get_pull_list()

        self.assertEqual(result['items_synced'], 1)
        self.assertEqual(items[0]['provider'], 'Weekly JSON')
        self.assertEqual(items[0]['series'], 'Batman')
        self.assertEqual(items[0]['issue_number'], '1')
        self.assertEqual(items[0]['title'], 'A New Beginning')

    def test_csv_body_sync_replaces_existing_provider_items(self):
        provider = save_provider('importlists', {
            'name': 'Weekly CSV',
            'implementation': 'csv',
            'enabled': True,
            'settings': {
                'body': (
                    'release_date,publisher,series,issue_number,title\n'
                    '2026-06-10,Marvel,Avengers,7,Final Host\n'
                )
            }
        })

        first = sync_import_list(provider['id'])
        second = sync_import_list(provider['id'])
        items = get_pull_list()

        self.assertEqual(first['items_synced'], 1)
        self.assertEqual(second['items_synced'], 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['series'], 'Avengers')

    def test_mylar_export_shape_syncs_to_pull_list(self):
        provider = save_provider('importlists', {
            'name': 'Mylar Export',
            'implementation': 'mylar',
            'enabled': True,
            'settings': {
                'body': (
                    '{"comics":[{"ComicName":"Saga",'
                    '"Issue_Number":"64","IssueName":"Chapter Sixty Four",'
                    f'"IssueDate":"{_date_from_now(8)}"}}]'
                    '}'
                )
            }
        })

        result = sync_import_list(provider['id'])
        items = get_pull_list()

        self.assertEqual(result['items_synced'], 1)
        self.assertEqual(items[0]['series'], 'Saga')
        self.assertEqual(items[0]['issue_number'], '64')
        self.assertEqual(items[0]['title'], 'Chapter Sixty Four')

    def test_comicvine_result_shape_syncs_to_pull_list(self):
        provider = save_provider('importlists', {
            'name': 'ComicVine List',
            'implementation': 'comicvine',
            'enabled': True,
            'settings': {
                'items': [{
                    'name': 'Daredevil',
                    'number': '3',
                    'store_date': _date_from_now(9),
                    'publisher': 'Marvel'
                }]
            }
        })

        result = sync_import_list(provider['id'])
        items = get_pull_list()

        self.assertEqual(result['items_synced'], 1)
        self.assertEqual(items[0]['series'], 'Daredevil')
        self.assertEqual(items[0]['issue_number'], '3')
        self.assertEqual(items[0]['publisher'], 'Marvel')

    def test_manual_pull_list_item_can_be_deleted(self):
        item = save_pull_list_item({
            'release_date': '2026-06-10',
            'publisher': 'DC Comics',
            'series': 'Batman',
            'issue_number': '1',
            'title': 'A New Beginning'
        })

        delete_pull_list_item(item['id'])

        self.assertEqual(get_pull_list(), [])

    def test_calendar_pull_list_syncs_enabled_import_lists(self):
        save_provider('importlists', {
            'name': 'Calendar JSON',
            'implementation': 'json',
            'enabled': True,
            'settings': {
                'items': [{
                    'release_date': _date_from_now(7),
                    'publisher': 'DC Comics',
                    'series': 'Batman',
                    'issue_number': '1',
                    'issue_title': 'A New Beginning'
                }]
            }
        })

        results = sync_enabled_import_lists(notify=False)
        items = get_calendar_pull_list(days=14)

        self.assertEqual(results[0]['items_synced'], 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['provider'], 'Calendar JSON')
        self.assertEqual(items[0]['series'], 'Batman')

    def test_calendar_pull_list_filters_dated_items_outside_window(self):
        save_pull_list_item({
            'release_date': _date_from_now(7),
            'publisher': 'DC Comics',
            'series': 'Batman',
            'issue_number': '1',
            'title': 'A New Beginning'
        })
        save_pull_list_item({
            'release_date': _date_from_now(60),
            'publisher': 'DC Comics',
            'series': 'Superman',
            'issue_number': '1',
            'title': 'Future State'
        })

        items = get_calendar_pull_list(days=14)

        self.assertEqual([item['series'] for item in items], ['Batman'])


if __name__ == '__main__':
    unittest.main()


class import_list_sync_task(import_list_sync):
    def test_task_syncs_enabled_import_lists_only(self):
        from backend.features import tasks
        from backend.features.tasks import SyncImportLists

        class FakeWebSocket:
            def emit(self, event):
                return None

        original_websocket = tasks.WebSocket
        tasks.WebSocket = FakeWebSocket
        self.addCleanup(lambda: setattr(tasks, 'WebSocket', original_websocket))

        enabled = save_provider('importlists', {
            'name': 'Enabled JSON',
            'implementation': 'json',
            'enabled': True,
            'settings': {
                'items': [{'series': 'Batman', 'issue_number': '1'}]
            }
        })
        save_provider('importlists', {
            'name': 'Disabled JSON',
            'implementation': 'json',
            'enabled': False,
            'settings': {
                'items': [{'series': 'Superman', 'issue_number': '1'}]
            }
        })

        task = SyncImportLists()
        task.run()
        items = get_pull_list()

        self.assertEqual(enabled['enabled'], True)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['provider'], 'Enabled JSON')
        self.assertEqual(items[0]['series'], 'Batman')


class pull_list_search_task(import_list_sync):
    def _seed_matched_issue(self):
        cursor = get_db()
        cursor.execute(
            "INSERT INTO root_folders(id, folder) VALUES(?, ?);",
            (1, '/tmp/library')
        )
        cursor.execute(
            """
            INSERT INTO volumes(
                id, comicvine_id, title, alt_title, year, monitored,
                quality_profile_id, root_folder, folder, special_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?);
            """,
            (
                1, 100, 'Batman', 'Batman', 2026, True, 1, 1,
                '/tmp/library/Batman', None
            )
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

    def test_search_pull_list_queues_matched_items_and_updates_status(self):
        from backend.features import tasks
        from backend.features.tasks import SearchPullList

        self._seed_matched_issue()
        provider = save_provider('importlists', {
            'name': 'Weekly JSON',
            'implementation': 'json',
            'enabled': True,
            'settings': {
                'items': [{'series': 'Batman', 'issue_number': '1'}]
            }
        })
        sync_import_list(provider['id'])
        calls = []

        class FakeWebSocket:
            def emit(self, event):
                return None

        def fake_auto_search(volume_id, issue_id=None):
            calls.append((volume_id, issue_id))
            return [{'link': 'https://example.invalid/batman-1'}]

        original_websocket = tasks.WebSocket
        original_auto_search = tasks.auto_search
        tasks.WebSocket = FakeWebSocket
        tasks.auto_search = fake_auto_search
        self.addCleanup(
            lambda: setattr(tasks, 'WebSocket', original_websocket)
        )
        self.addCleanup(
            lambda: setattr(tasks, 'auto_search', original_auto_search)
        )

        result = SearchPullList().run()
        items = get_pull_list()

        self.assertEqual(calls, [(1, 1)])
        self.assertEqual(
            result,
            [('https://example.invalid/batman-1', 1, 1, False, {})]
        )
        self.assertEqual(items[0]['status'], 'queued')
