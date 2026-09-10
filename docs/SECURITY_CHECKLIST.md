# Production security checklist

This checklist records the controls implemented in the repository and the
deployment settings that still belong to the operator. It contains no real
credentials.

## Implemented in code

- [x] Clerk session tokens are obtained by the Clerk SDK and sent as bearer
  tokens; application code does not persist authentication tokens in
  `localStorage` or cookies.
- [x] The API verifies Clerk session tokens, restricts authorized parties to
  `HSK_FRONTEND_ORIGINS`, requires verified primary email addresses, and keeps
  roles and account status server-side.
- [x] Deprecated password login and registration endpoints return `410 Gone`.
  The retained password helper uses bcrypt with a work factor of 12 for legacy
  data only; Clerk owns password policy, session expiry, and refresh rotation.
- [x] Student and administrator routes use server-side authorization
  dependencies. A client-supplied score, role, deadline, or correctness value
  is never trusted.
- [x] Exam starts are serialized per user and test, deadlines are checked by
  the API, answers are validated against the attempt, listening limits are
  counted server-side, and final scoring is server-authoritative.
- [x] SQLAlchemy or the Turso adapter binds query parameters rather than
  concatenating user input into SQL.
- [x] CORS uses an explicit origin list, a bounded method/header list, and no
  credentialed cross-origin cookies.
- [x] API, authentication, material, and administrator endpoints have bounded
  request-rate policies and return standard rate-limit headers.
- [x] JSON and upload request bodies are bounded, including chunked bodies.
- [x] Uploaded exam archives are checked by extension, MIME type, ZIP magic,
  path/depth/entry limits, case-collisions, encryption, symlinks, compression
  ratio, extracted size, and PDF/MP3 content signatures.
- [x] An optional fail-closed malware-scanner command is available through
  `HSK_MALWARE_SCAN_COMMAND`; the upload path is passed as a separate process
  argument and never through a shell.
- [x] Private study content uses user-scoped, expiring grants and private B2
  signed redirects. Protected material paths are excluded from public media.
- [x] Request IDs, safe production error responses, structured audit events,
  HTTPS enforcement, HSTS, CSP, anti-framing, MIME-sniffing protection,
  referrer policy, and permissions policy are implemented for the API.
- [x] The SPA has an enforced CSP baseline, contextual Vue escaping, no
  `v-html`, safe external-link attributes, and no frontend secrets.
- [x] Production settings fail closed for debug mode, HTTP frontend origins,
  weak/reused signing secrets, disabled HTTPS, privileged/default MySQL
  credentials, missing Clerk settings, missing Turso settings, or incomplete
  enabled B2 settings.

## Required Render backend settings

Set these as secret environment variables on the backend Web Service:

```dotenv
HSK_ENVIRONMENT=production
HSK_DEBUG=false
HSK_FORCE_HTTPS=true
HSK_FRONTEND_ORIGINS=https://YOUR_FRONTEND_HOST
HSK_JWT_SECRET=GENERATE_AT_LEAST_32_RANDOM_CHARACTERS
HSK_MATERIAL_ACCESS_SECRET=GENERATE_A_DIFFERENT_RANDOM_VALUE

CLERK_SECRET_KEY=YOUR_PRODUCTION_CLERK_SECRET

HSK_DATABASE_BACKEND=turso
TURSO_DATABASE_URL=libsql://YOUR_DATABASE.turso.io
TURSO_AUTH_TOKEN=YOUR_PRIVATE_TOKEN

HSK_B2_ENABLED=true
HSK_B2_BUCKET_NAME=YOUR_PRIVATE_BUCKET
HSK_B2_ENDPOINT_URL=https://s3.YOUR_REGION.backblazeb2.com
HSK_B2_REGION=YOUR_REGION
HSK_B2_KEY_ID=YOUR_READ_ONLY_BUCKET_KEY_ID
HSK_B2_APPLICATION_KEY=YOUR_READ_ONLY_BUCKET_KEY
```

Use separate publisher credentials for uploads. The running API should have a
bucket-restricted read-only key. Do not put any value above in the frontend
service.

Generate each application signing secret independently:

```powershell
py -3.11 -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Required Render static-site controls

In the frontend Static Site, keep the Vue Router rule:

| Source | Destination | Action |
| --- | --- | --- |
| `/*` | `/index.html` | Rewrite |

Under **Headers**, add the following rules for path `/*`:

| Header | Value |
| --- | --- |
| `Content-Security-Policy` | `default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self' https:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' https: wss:; media-src 'self' blob: https:; frame-src 'self' blob: https:; worker-src 'self' blob:` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Cross-Origin-Opener-Policy` | `same-origin-allow-popups` |

The checked-in meta CSP is a compatible baseline. `frame-ancestors` only takes
effect when sent as an HTTP header, which is why the Render rule is still
required. After the production Clerk Frontend API and B2 download hosts are
known, replace broad `https:` sources with an explicit host allowlist. Clerk
requires its Frontend API host, `https://challenges.cloudflare.com`, and
`https://*.protect.clerk.com` in the applicable directives; verify sign-in,
sign-up, social OAuth, the user menu, PDF viewing, audio, and downloads after
tightening.

Add a second header rule for `/assets/*`:

| Header | Value |
| --- | --- |
| `Cache-Control` | `public, max-age=31536000, immutable` |

Do not apply immutable caching to `/index.html`, because it must reference the
new hashed asset names after every deploy.

## Provider and operational checks

- [ ] Use a Clerk production instance and add only the real frontend domains
  to its allowed origins/redirect URLs. Configure a Clerk custom domain where
  possible so auth cookies are first-party.
- [ ] Confirm `HSK_FRONTEND_ORIGINS` contains exact origins only—no path, query,
  trailing wildcard, or credentials.
- [ ] Keep the B2 bucket private, Object Lock/lifecycle settings intentional,
  CORS narrowly scoped, and application keys bucket-specific.
- [ ] Enable a production malware scanner or scanning service by setting
  `HSK_MALWARE_SCAN_COMMAND`; test both a clean archive and the EICAR test file
  in a non-production bucket before allowing administrator uploads.
- [ ] Use a dedicated least-privilege MySQL account if MySQL is selected. Never
  deploy with `root`, `admin`, or a default password.
- [ ] Route `hsk.audit` JSON logs to a retained log drain and alert on repeated
  rate limits, rejected audio replays, account changes, imports, and unusual
  attempt-start volume.
- [ ] Rotate Clerk, Turso, B2, and signing secrets after accidental exposure.
  Signed media grants become invalid when the material signing secret rotates.
- [ ] Back up the database, verify restore procedures, and retain migration
  snapshots according to the project's data policy.
- [ ] Review dependency alerts and run the full test suite before every release.

The in-memory rate limiter is intentionally dependency-free and bounded. It is
effective per API process. If Render is scaled to multiple workers or replicas,
replace it with a shared Redis-compatible limiter so quotas are global.

## Release verification

```powershell
# Backend liveness and root service information
irm https://YOUR_BACKEND_HOST/api/health
irm https://YOUR_BACKEND_HOST/

# Review headers (PowerShell 7+)
curl.exe -I https://YOUR_FRONTEND_HOST/
curl.exe -I https://YOUR_BACKEND_HOST/api/health
```

Also verify that an unapproved origin receives no CORS allow-origin header,
student tokens receive `403` on `/api/admin/*`, expired attempts reject answer
changes, and private B2 object URLs cannot be fetched without a fresh grant.
