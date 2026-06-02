# Usenet Integration Reconnaissance

Kapowarr is a Python/Flask backend application with Jinja templates and vanilla JavaScript frontend assets. API routes are defined in `frontend/api.py`, while backend behavior is split between `backend/features`, `backend/implementations`, `backend/base`, and `backend/internals`.

Configuration is stored in the SQLite `config` table and represented by dataclasses in `backend/internals/settings.py`. Public settings are exposed through `GET/PUT /api/settings`; credentials are masked using the shared `Constants.CREDENTIAL_REPLACEMENT` pattern.

Download clients already have an external-client abstraction in `backend/base/definitions.py` and `backend/implementations/external_clients.py`. qBittorrent and Transmission implement this abstraction, with remote path mappings in `backend/implementations/remote_mapping.py`.

The active download queue lives in `backend/features/download_queue.py` and persists restartable queue rows in the `download_queue` table. External downloads are represented by `ExternalDownload` implementations and polled by a background thread.

Import/post-processing is handled through `backend/features/post_processing.py` and the existing file-processing/matching code, so completed external downloads should update their produced file/folder path and then reuse the existing post-processing flow.

Manual and automatic search live in `backend/features/search.py`. Search providers implement `SearchSource`, return `SearchResultData`, and are matched by `backend/implementations/matching.py` against volume/issue metadata.

Database schema and migrations live in `backend/internals/db.py` and `backend/internals/db_migration.py`. Most configuration additions can use the existing config table without schema migrations.

Logging uses the shared `LOGGER` from `backend/base/logging.py`. Errors surfaced through the API generally subclass `KapowarrException` in `backend/base/custom_exceptions.py`; download-client connectivity/auth failures use `ClientNotWorking` and `CredentialInvalid`.

Tests currently use Python `unittest` under `tests/Tbackend`, with coverage focused on backend behavior such as filename extraction.
