# HSK Mock Test Platform

A full-stack HSK learning application for taking timed mock exams and studying
HSK course materials. The project combines a Vue 3 single-page application,
a FastAPI API, Clerk authentication, SQLAlchemy persistence, and private media
delivery from either the local filesystem or Backblaze B2.

The code supports two deployment modes:

- Local development with MySQL 8 and local media files.
- Cloud deployment with Turso/libSQL and a private Backblaze B2 bucket.

> This repository contains source code only. Exam bundles, books, audio,
> generated media, database snapshots, cloud reports, and credentials are
> intentionally excluded from Git. You must supply content that you are legally
> permitted to use and distribute.

## Current capabilities

### Mock exams

- Published HSK 1-6 test catalog and timed exam workspace.
- Listening, reading, and writing question support.
- Server-authoritative deadlines and automatic expiry submission.
- Answer autosave, local draft recovery, and resume-in-progress behavior.
- API-enforced listening replay limits.
- Section-normalized scores, pass/fail results, and answer review.
- Student history, accuracy, score, and weak-section dashboard.
- Administrator bundle import, publication, archival, test settings, roles,
  and account enable/disable controls.
- Idempotent imports that preserve existing attempts and relationships.

### Study library

- HSK 2.0 Levels 1-6 and supplied HSK 3.0 course resources.
- New HSK vocabulary PDFs for Levels 1-6 and combined Levels 7-9.
- Embedded PDF reader with a full-width layout for PDF-only resources.
- Lesson-grouped audio with seeking, speed control, and automatic next-track
  playback where matching audio is supplied.
- Authenticated PDF, audio-track, audio-ZIP, and complete-pack downloads.
- Private expiring media links; source paths and storage credentials are never
  exposed to the browser.
- Safe streaming ZIP generation without staging multi-gigabyte duplicate files.

### Authentication and authorization

- Clerk-hosted sign-in and sign-up inside the branded Vue interface.
- Server-side Clerk session-token verification.
- Authorized-party allowlist enforced by FastAPI.
- Verified-email linking to an existing local profile.
- Server-owned student/admin roles and account status.

## Verified content snapshot

The private development/cloud dataset verified on 2026-09-08 contains:

| Content | Count |
| --- | ---: |
| Published mock tests | 26 |
| Exam questions | 2,023 |
| Selectable choices/order tokens | 7,605 |
| Study books/PDFs | 33 |
| Study pages | 4,603 |
| Audio tracks | 1,215 |
| Lesson/audio groups | 346 |

These records and media files are not committed to this repository.

## Architecture

```text
Vue 3 / Clerk
      |
      | Bearer session token + JSON API
      v
FastAPI / SQLAlchemy
      |                         |
      | exam and user data      | signed private media redirects
      v                         v
MySQL 8 or Turso/libSQL     local storage or Backblaze B2
```

### Technology stack

- Frontend: Vue 3, Vite, Pinia, Vue Router, Axios, Clerk Vue, Element Plus,
  Tailwind CSS.
- Backend: Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Clerk Backend SDK,
  PyMuPDF, pdfplumber, Pillow, boto3.
- Databases: MySQL 8 locally, or Turso's SQLite-compatible libSQL service.
- Object storage: local filesystem or private Backblaze B2 through its
  S3-compatible API.
- Tests: pytest and Node's built-in test runner.

Turso is not a MySQL service. The backend selects either the MySQL adapter or
the Turso/libSQL adapter with `HSK_DATABASE_BACKEND`.

## Repository layout

```text
backend/                 FastAPI application, models, API routes, migrations
backend/tests/           Backend, importer, storage, and database tests
database/                Local MySQL bootstrap SQL
docs/                    Content audit and cloud migration/runbook
frontend/                Vue application
frontend/tests/          Frontend normalization/compatibility tests
scripts/                 Import, migration, upload, role, and verification tools
storage/                 Generated output (ignored except .gitkeep)
uploads/                 Temporary imports (ignored except .gitkeep)
```

The following required content directories are also ignored:

```text
HSK_mock_test_bundles_exam_answers_audio_file/
HSK_Materials/
```

See [the materials audit](docs/STUDY_MATERIALS_AUDIT.md) for the expected study
content mapping and [the cloud runbook](docs/CLOUD_MIGRATION.md) for the verified
Turso/B2 workflow.

## Prerequisites

- Python 3.11.
- Node.js 20 or newer and npm.
- MySQL 8 for local database mode, or a Turso database for cloud mode.
- A Clerk application.
- Backblaze B2 only when cloud media mode is enabled.

The project has been exercised on Windows 11 with PowerShell. The Render
commands below use its Linux shell environment.

## Local setup with MySQL

### 1. Clone the repository

```powershell
git clone https://github.com/DamsCode444/HSK_Mock.git
cd HSK_Mock
```

### 2. Create local environment files

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

Edit `backend/.env` and provide:

- A local `HSK_DATABASE_URL` using your own MySQL username and password.
- `CLERK_SECRET_KEY` from the Clerk dashboard.
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` from the same Clerk application.
- Strong, different values for `HSK_JWT_SECRET` and
  `HSK_MATERIAL_ACCESS_SECRET`.

Edit `frontend/.env.local` and set `VITE_CLERK_PUBLISHABLE_KEY`. This key is
designed to be public. Never put `CLERK_SECRET_KEY`, database credentials,
Turso tokens, or B2 keys in a frontend environment variable.

Generate suitable local signing secrets with Python:

```powershell
py -3.11 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Run it twice and use a different output for each signing-secret setting.

### 3. Create the MySQL database

```powershell
mysql -h 127.0.0.1 -P 3306 -u root -p -e "SOURCE database/001_create_database.sql"
```

Use the same credentials in `HSK_DATABASE_URL`. The SQL file creates the
`hsk_mock_tester` database with `utf8mb4` and is safe to run again.

### 4. Install and migrate the backend

```powershell
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

Push-Location backend
.\.venv\Scripts\alembic.exe upgrade head
Pop-Location
```

### 5. Install the frontend

```powershell
Push-Location frontend
npm ci
Pop-Location
```

### 6. Add and import private content

Place the source bundles in their ignored directories. Inspect detected exam
bundles before importing:

```powershell
backend\.venv\Scripts\python.exe scripts\import_hsk_tests.py --list
backend\.venv\Scripts\python.exe scripts\import_hsk_tests.py --all
backend\.venv\Scripts\python.exe scripts\import_hsk_materials.py
```

Useful exam-import alternatives:

```powershell
# Import one exam only
backend\.venv\Scripts\python.exe scripts\import_hsk_tests.py --test-code H11329

# Reparse changed source even if the saved fingerprint matches
backend\.venv\Scripts\python.exe scripts\import_hsk_tests.py --all --force
```

The materials importer rejects unknown files rather than silently omitting
them. It validates PDFs, safe ZIP paths, audio mappings, duplicate IDs, image
types, decompression limits, and source/storage path confinement.

### 7. Start the application

Terminal 1:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

Open:

- Application: <http://127.0.0.1:5173>
- Study library: <http://127.0.0.1:5173/materials>
- Vocabulary library: <http://127.0.0.1:5173/materials?edition=vocabulary>
- API documentation: <http://127.0.0.1:8000/docs>
- Health endpoint: <http://127.0.0.1:8000/api/health>

## Clerk behavior

The first authenticated call to `/api/auth/me` creates a local profile or links
an existing profile whose verified email matches. New users receive the student
role. To promote an already linked account:

```powershell
backend\.venv\Scripts\python.exe scripts\set_user_role.py --email you@example.com --role admin
```

The command refuses unknown or unlinked profiles. Password-based API login and
registration are retired; Clerk owns interactive authentication.

For production, add the deployed frontend domain to Clerk and set the same
origin in `HSK_FRONTEND_ORIGINS`.

## Cloud mode: Turso and Backblaze B2

Real cloud credentials belong only in ignored `backend/.env` or the deployment
provider's secret settings:

```dotenv
HSK_DATABASE_BACKEND=turso
TURSO_DATABASE_URL=libsql://YOUR_DATABASE.turso.io
TURSO_AUTH_TOKEN=YOUR_TURSO_TOKEN

HSK_B2_ENABLED=true
HSK_B2_BUCKET_NAME=YOUR_PRIVATE_BUCKET
HSK_B2_ENDPOINT_URL=https://s3.YOUR_REGION.backblazeb2.com
HSK_B2_REGION=YOUR_REGION
HSK_B2_KEY_ID=YOUR_BUCKET_KEY_ID
HSK_B2_APPLICATION_KEY=YOUR_BUCKET_APPLICATION_KEY
HSK_B2_SIGNED_URL_TTL_SECONDS=3600
```

Use a bucket-restricted key. A read-only bucket key is preferred for the
running API; use a separate write-enabled key only for publication.

### Migrate MySQL data to Turso

The migration script first creates a private, ignored SQLite snapshot. The
default invocation is a dry run:

```powershell
backend\.venv\Scripts\python.exe scripts\migrate_to_turso.py
backend\.venv\Scripts\python.exe scripts\migrate_to_turso.py --apply
```

The target must be empty or already owned by the same migration fingerprint.
The script never overwrites unrelated rows and verifies row equality, foreign
keys, and database integrity.

### Publish media to B2

Generate the materials catalog, run a preview, and then apply:

```powershell
backend\.venv\Scripts\python.exe scripts\import_hsk_materials.py
backend\.venv\Scripts\python.exe scripts\upload_cloud_media.py --replace-manifest
backend\.venv\Scripts\python.exe scripts\upload_cloud_media.py --apply --replace-manifest
```

The uploader does not delete cloud objects and refuses to overwrite differing
media. It uploads and verifies new media first, backs up the previous manifest,
rechecks its version, and publishes the new manifest last. Run only one
publisher at a time.

Backblaze `GetObject` and `HeadObject` calls count as Class B reads. If a B2
account cap is reached, do not re-upload. Increase the cap deliberately or wait
for its daily reset, then run the focused read-only check:

```powershell
backend\.venv\Scripts\python.exe scripts\verify_vocabulary_cloud.py
```

## Deploy on Render

### Backend web service

Use the repository root as the service root so deployment and maintenance
scripts remain available.

- Build command: `pip install -r backend/requirements.txt`
- Pre-deploy command: `cd backend && alembic upgrade head`
- Start command: `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT`
- Health path: `/api/health`

Set the Turso, B2, and Clerk variables above plus:

```dotenv
HSK_ENVIRONMENT=production
HSK_DEBUG=false
HSK_FRONTEND_ORIGINS=https://YOUR_FRONTEND_DOMAIN
HSK_JWT_SECRET=YOUR_RANDOM_SECRET
HSK_MATERIAL_ACCESS_SECRET=YOUR_DIFFERENT_RANDOM_SECRET
```

The health route is a liveness check; it does not read Turso or B2. Cloud media
mode does not require a persistent Render disk.

### Frontend static site

- Root directory: `frontend`
- Build command: `npm ci && npm run build`
- Publish directory: `dist`
- Rewrite: `/*` to `/index.html`

Set:

```dotenv
VITE_API_BASE_URL=https://YOUR_BACKEND_DOMAIN/api
VITE_MEDIA_ORIGIN=https://YOUR_BACKEND_DOMAIN
VITE_CLERK_PUBLISHABLE_KEY=YOUR_CLERK_PUBLISHABLE_KEY
```

Never add backend secrets to the frontend service.

## Tests and validation

Because a developer's real `.env` may enable cloud services, force isolated
local settings when running backend tests:

```powershell
Push-Location backend
$env:HSK_DATABASE_BACKEND = "mysql"
$env:HSK_B2_ENABLED = "false"
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:HSK_DATABASE_BACKEND, Env:HSK_B2_ENABLED
Pop-Location

Push-Location frontend
npm test
npm run build
Pop-Location
```

Latest local result: 77 backend tests and 3 frontend tests pass; the production
frontend build completes with only Vite's non-blocking large-chunk warning.

The test suite covers authentication linking, authorization, imports, scoring,
answer privacy, exam start/resume/autosave/submission, playback limits, Turso
transactions, B2 publication safety, private material grants, byte ranges,
streamed ZIP integrity, and vocabulary compatibility.

## Main API groups

| Route prefix | Purpose |
| --- | --- |
| `/api/auth` | Current Clerk-linked profile |
| `/api/tests` | Public test catalog and exam start |
| `/api/attempts` | Answers, listening events, and submission |
| `/api/results` | Submitted attempt results and review |
| `/api/dashboard` | Student progress summary |
| `/api/materials` | Catalog, private file grants, and bundles |
| `/api/admin` | Protected administrative operations |

Open `/docs` on a running API for the generated OpenAPI explorer.

## Security and content notes

- `.env`, database files, cloud reports, generated media, source books/audio,
  logs, private keys, build output, and dependencies are ignored by Git.
- Public catalog metadata contains no filesystem paths or storage credentials.
- Study documents and audio require a Clerk-authenticated grant and use
  short-lived, user-scoped URLs.
- ZIP import and streaming paths are normalized and confined to approved roots.
- B2 media is private; browser access uses expiring signed redirects.
- Do not commit tokens or signed URLs. Rotate any credential that has ever been
  pasted into an issue, commit, screenshot, or public chat.
- The supplied material directories did not include a redistribution license.
  Confirm your rights before serving books, audio, exam PDFs, or answer files to
  users.

## License

No open-source license has been granted for this repository. Copyright remains
with the respective code and content owners. Add an explicit license before
inviting third-party reuse or contributions.
