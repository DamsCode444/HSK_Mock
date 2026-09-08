# Cloud migration: Backblaze B2 and Turso

The original local MySQL database is preserved. An additional consistent SQLite
snapshot is stored in the ignored `.cloud-transfer/mysql-before-turso.sqlite3`.
This snapshot contains account data; keep it private and do not upload it to Git.

## Transferred data

- B2 bucket: `HSKMOCKTEST`, private, endpoint `https://s3.us-east-005.backblazeb2.com`.
- `HSK_Materials/`: original study PDFs, covers, and audio.
- `storage/`: generated exam media and the study manifest/covers/extracted tracks.
- `exam_bundles/`: the original mock-test bundles, retained as a private source backup.
- Initial upload: 1,861 files, 6,547,232,131 bytes. Its report is preserved at
  `.cloud-transfer/b2-before-vocabulary-20260908.json`.
- Latest upload report: `.cloud-transfer/b2-upload-report.json`.
- Vocabulary publication verified on 2026-09-08: 1,876 current objects,
  6,567,870,524 bytes, zero upload failures. Fifteen new objects were added
  (eight original files and seven thumbnails); the catalog was published last.
- Post-upload full-download checks were subsequently blocked by B2's configured
  download bandwidth / Class B transaction cap. All seven covers and Levels 1–5
  passed live checks first. Levels 6, 7–9, and the comparison PNG still need the
  final full-download verification after the account cap permits reads again.
- Turso report: `.cloud-transfer/turso-migration-report.json`.
- Copied application tables: users, hsk_tests, questions, options, attempts,
  answers, attempt_audio_plays, import_logs, plus alembic_version.
- All source IDs, JSON data, timestamps, and relationships are preserved.

The transfer scripts do not overwrite differing cloud rows/media objects or delete
remote-only data. Only an explicit `--replace-manifest` allows catalog replacement,
after backing up its old version and verifying all other uploads.
`upload_cloud_media.py` compares SHA-256 metadata and sizes,
then verifies range reads after uploads. `migrate_to_turso.py` compares every
row with its snapshot and checks foreign keys and database integrity.

## Backend configuration

Real credentials belong only in ignored `backend/.env` or the hosting provider's
secret environment settings. Example files contain placeholders only.

```dotenv
HSK_DATABASE_BACKEND=turso
TURSO_DATABASE_URL=libsql://YOUR_DATABASE.turso.io
TURSO_AUTH_TOKEN=YOUR_DATABASE_TOKEN
HSK_B2_ENABLED=true
HSK_B2_BUCKET_NAME=HSKMOCKTEST
HSK_B2_ENDPOINT_URL=https://s3.us-east-005.backblazeb2.com
HSK_B2_REGION=us-east-005
HSK_B2_KEY_ID=YOUR_KEY_ID
HSK_B2_APPLICATION_KEY=YOUR_APPLICATION_KEY
HSK_JWT_SECRET=YOUR_RANDOM_SECRET
HSK_MATERIAL_ACCESS_SECRET=A_SEPARATE_RANDOM_SECRET
```

`HSK_DATABASE_URL` remains the original MySQL connection for recovery and source
exports. It is not used by the running API when `HSK_DATABASE_BACKEND=turso`.
Turso is SQLite/libSQL-compatible, not MySQL; do not put its URL in that MySQL field.

Remote SQL uses Turso's HTTPS pipeline protocol, parameter binding, per-connection
transaction batons, and foreign-key enforcement. The HTTP client honors existing
OS/environment proxy settings; no machine-wide proxy settings are modified.
Exam read-modify-write operations acquire `BEGIN IMMEDIATE` before reading.
Contention returns a retryable error instead of allowing lost updates.

B2 serves books/audio through expiring, authenticated redirects. Covers and public
exam media use narrowly scoped signed redirects. The materials catalog is cached
in memory from B2. Complete ZIP packs stream remote objects with bounded memory;
they do not stage the library on the backend filesystem. Large pack downloads still
consume backend outbound bandwidth and can be interrupted by a service restart.

## Render settings

Backend root directory: leave blank, so `scripts/` remains available.

- Build: `pip install -r backend/requirements.txt`
- Pre-deploy: `cd backend && alembic upgrade head`
- Start: `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
- Health path: `/api/health` (liveness only, not a database/media readiness check).
- Set the cloud variables above, `HSK_ENVIRONMENT=production`, `HSK_DEBUG=false`,
  `CLERK_SECRET_KEY`, and `HSK_FRONTEND_ORIGINS=["https://YOUR_FRONTEND_DOMAIN"]`.

Frontend root directory: `frontend`; build `npm ci && npm run build`; publish `dist`.
Set `VITE_API_BASE_URL=https://YOUR_API/api`, `VITE_MEDIA_ORIGIN=https://YOUR_API`,
and `VITE_CLERK_PUBLISHABLE_KEY`. Add the SPA rewrite `/*` to `/index.html`.
No database or B2 secrets belong in frontend variables.

The existing cloud media library needs no persistent Render disk. Local imports,
source edits, or new uploads are a separate publication workflow: import locally,
review changes, upload new/versioned media, and update the cloud catalog deliberately.
The transfer helper refuses to overwrite changed media keys. Catalog replacement
has its own explicit, backed-up publication path, described below.
Use a bucket-restricted read-only B2 key for normal runtime when available.

Clerk production keys must match its production instance and configured custom
domain. Switching Clerk instances does not automatically migrate Clerk accounts.

## Recovery and verification

To return to the original local data, set `HSK_DATABASE_BACKEND=mysql` and
`HSK_B2_ENABLED=false`, then restart the backend. This is a point-in-time fallback:
new cloud attempts will not be present in the old MySQL database automatically.

Run local tests with `HSK_DATABASE_BACKEND=mysql` and `HSK_B2_ENABLED=false` so test
fixtures remain isolated from cloud services. Use the dedicated verification script
only deliberately: it creates a uniquely named QA account and removes that account
and its own attempts after checking start/resume/save/playback limits/submission.

Never commit credentials, the database snapshot, or signed download URLs. If an
example file containing credentials was previously pushed/shared, rotate those
credentials in the provider dashboard.

## Adding vocabulary and future study resources

`HSK_Materials/New_HSK_Vocabulary-1-9/` is an optional additional collection:
seven PDFs (477 pages) for Levels 1–6 and combined Levels 7–9, plus the supplied
comparison PNG. It appears under **Study materials → Vocabulary**. The chart is
labeled as a supplied reference, not verified current official exam requirements.
The PDFs use full-width reading without an audio sidebar; no audio was supplied.

Materials live in B2 with a catalog manifest, not as binary files in Turso. Adding
these resources requires no database migration and does not change exam attempts.
The complete library now contains 33 PDFs, 4,603 pages, and 1,215 audio tracks.
Local entry point: `http://localhost:5173/materials?edition=vocabulary`.

Run from the project root, using the private credentials in `backend/.env`:

```powershell
backend/.venv/Scripts/python.exe scripts/import_hsk_materials.py
backend/.venv/Scripts/python.exe scripts/upload_cloud_media.py --replace-manifest
backend/.venv/Scripts/python.exe scripts/upload_cloud_media.py --apply --replace-manifest
```

Review the preview first. New folders or naming schemes require importer mappings;
unknown files are rejected instead of silently omitted. The uploader verifies all
overlapping objects, uploads new media, then publishes the manifest **last**. A
failed media upload leaves the old cloud catalog current. Prior catalog bytes and
ETag/version/hash evidence are saved in `.cloud-transfer/manifests/`.

Run only one publisher at a time, including across machines. A workspace lock and
last-moment version recheck guard against concurrent changes; these are not a
cross-machine atomic compare-and-swap guarantee. Backblaze's documented
[Put Object headers](https://www.backblaze.com/apidocs/s3-put-object) do not list
`If-Match`, so this workflow does not assume AWS-only conditional-write support.

Restart the backend after importer/API code changes. An unchanged running API
refreshes its remote catalog cache within 60 seconds. Rebuild/redeploy the frontend
to show new interface features. These steps do not deploy the site to Render.

`scripts/verify_vocabulary_cloud.py` checks the running local cloud-backed API,
reads every new original file fully and compares its SHA-256, checks downloads,
cover ranges, and anonymous access rejection. It uses an existing active user for
private signed-grant checks and makes no database writes. Its report is private
at `.cloud-transfer/vocabulary-verification.json`; tokens are never logged by it.

If B2 reports `download bandwidth or transaction (Class B) cap exceeded`, do not
re-upload the library or repeatedly retry. Review **B2 Cloud Storage → Caps &
Alerts** for the category that reached its limit. Raising a cap may permit charges;
choose a budget deliberately, or wait for the daily reset. Backblaze documents the
[daily reset at 00:00 GMT](https://www.backblaze.com/docs/en/cloud-storage-data-caps-and-alerts).
Media and catalog reads may fail until then, even though uploads are intact.
Preview and apply each check existing objects with read transactions; a complete
library audit consumes quota. Run the focused vocabulary verification after the
cap is resolved, not another complete upload audit.
