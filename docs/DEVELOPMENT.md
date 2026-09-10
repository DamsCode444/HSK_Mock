# Development guide

Setup, configuration, deployment, and API reference for the HSK Mock Test
Platform. The public project overview lives in the [README](../README.md).

- Live application: <https://hsk-mock-1.onrender.com/>

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

## Backend environment reference

`backend/.env.example` is the source of truth for local defaults. The groups
below are the settings you are most likely to change.

### Core

```dotenv
HSK_APP_NAME=HSK Mock Test Platform
HSK_ENVIRONMENT=development
HSK_DEBUG=true
HSK_DATABASE_URL=mysql+pymysql://root:change_me@127.0.0.1:3306/hsk_mock_tester?charset=utf8mb4
HSK_FRONTEND_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
HSK_FORCE_HTTPS=false
HSK_JWT_SECRET=replace-with-a-long-random-value
HSK_JWT_ALGORITHM=HS256
HSK_ACCESS_TOKEN_MINUTES=120
```

### Rate limits and request bounds

```dotenv
HSK_RATE_LIMIT_ENABLED=true
HSK_RATE_LIMIT_MAX_CLIENTS=10000
HSK_RATE_LIMIT_API_PER_MINUTE=300
HSK_RATE_LIMIT_AUTH_PER_MINUTE=30
HSK_RATE_LIMIT_MATERIAL_PER_MINUTE=60
HSK_RATE_LIMIT_ADMIN_PER_MINUTE=60
HSK_MAX_JSON_BODY_KB=64
```

### Storage and imports

```dotenv
HSK_SOURCE_BUNDLE_ROOT=../HSK_mock_test_bundles_exam_answers_audio_file
HSK_MATERIALS_ROOT=../HSK_Materials
HSK_STORAGE_ROOT=../storage
HSK_MATERIALS_STORAGE_ROOT=../storage/materials
HSK_MATERIALS_MANIFEST_PATH=../storage/materials/manifest.json
HSK_MATERIAL_ACCESS_SECRET=replace-with-a-separate-long-random-value
HSK_MATERIAL_ACCESS_TTL_SECONDS=3600
HSK_MAX_UPLOAD_MB=300
HSK_UPLOAD_ZIP_MAX_FILES=2000
HSK_UPLOAD_ZIP_MAX_RATIO=100
HSK_MALWARE_SCAN_TIMEOUT_SECONDS=60
# Optional production scanner; the uploaded file path is appended automatically.
# HSK_MALWARE_SCAN_COMMAND=clamdscan --no-summary
```

### Clerk credentials

Copy these from the Clerk dashboard; never commit real values.

```dotenv
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_your_publishable_key
CLERK_SECRET_KEY=sk_test_your_secret_key
```

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
HSK_FORCE_HTTPS=true
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
- Rewrite: source `/*`, destination `/index.html`, action `Rewrite`

Set:

```dotenv
VITE_API_BASE_URL=https://YOUR_BACKEND_DOMAIN/api
VITE_MEDIA_ORIGIN=https://YOUR_BACKEND_DOMAIN
VITE_CLERK_PUBLISHABLE_KEY=YOUR_CLERK_PUBLISHABLE_KEY
```

Never add backend secrets to the frontend service.

Configure the static site's CSP, anti-framing, MIME-sniffing, referrer,
permissions, HSTS, opener, and immutable asset-cache headers exactly as listed
in the [production security checklist](SECURITY_CHECKLIST.md). The checked-in
HTML CSP is a compatible baseline, but `frame-ancestors` must be delivered as a
real response header by Render.

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

Latest local result: 105 backend tests and 3 frontend tests pass; the production
frontend build completes without an oversized-chunk warning. The local mobile
Lighthouse audit scores 93 Performance, 100 Accessibility, and 100 SEO; see the
[performance report](PERFORMANCE_REPORT.md) for conditions and remaining
production checks.

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
