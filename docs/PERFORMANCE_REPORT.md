# Frontend performance report

Measured on 2026-09-10 against a local Vite production preview using Lighthouse
mobile defaults and the Clerk development instance.

## Result

| Lighthouse category | Score |
| --- | ---: |
| Performance | **93** |
| Accessibility | **100** |
| SEO | **100** |
| Best Practices | 79 |

| Core metric | Result |
| --- | ---: |
| First Contentful Paint | 1.7 s |
| Largest Contentful Paint | 2.1 s |
| Speed Index | 1.7 s |
| Total Blocking Time | 260 ms |
| Cumulative Layout Shift | 0 |
| Time to Interactive | 3.4 s |

The requested Lighthouse performance target above 90 is met locally. Best
Practices is reduced by two third-party Cloudflare cookies reported from the
Clerk **development** Frontend API domain. Re-run the audit with a Clerk
production instance/custom domain and the deployed HTTPS origins before using
that score as a production release gate.

## Bundle improvement

| Shared asset | Before | After | Gzip reduction |
| --- | ---: | ---: | ---: |
| Initial JavaScript | 1,168.90 kB / 384.06 kB gzip | 265.23 kB / 95.52 kB gzip | 75.1% |
| Initial shared CSS | 413.58 kB / 58.93 kB gzip | 69.50 kB / 14.16 kB gzip | 76.0% |

The home route adds about 6.3 kB gzip JavaScript and 2.9 kB gzip CSS. Vite's
oversized-chunk warning has been eliminated.

## Implemented optimizations

- Vue route components are lazy-loaded and kept in separate production chunks.
- Element Plus components and their styles are imported on demand with the
  official resolver instead of registering the entire library up front.
- Programmatic Element Plus services use narrow module entry points.
- Public routes paint immediately while Clerk session discovery continues in
  the background; protected routes still wait for a definitive auth state.
- Below-the-fold home sections use `content-visibility`, and the default test
  catalog progressively renders six cards at a time.
- Material catalog and collection requests use bounded in-memory caches with
  request de-duplication.
- Book covers and answer images use native lazy loading/async decoding; the
  hero cover is explicitly high priority.
- Audio uses metadata preloading rather than downloading full lesson files on
  initial render.
- Loading skeletons reserve space, charts use SVG rather than a large charting
  dependency, and animations honor `prefers-reduced-motion`.
- Hashed Vite assets are ready for one-year immutable CDN caching on Render.
- A valid `robots.txt`, stable dimensions, and corrected text contrast produce
  100 Accessibility and SEO scores in the local audit.

## Remaining production checks

- The supplied 1,280 px PNG favicon is about 923 kB and is the largest cold-load
  transfer. It has been preserved exactly as supplied. Export a visually
  reviewed 32–64 px favicon plus a 180 px Apple touch icon to reduce repeat and
  mobile transfer size without changing the logo.
- Measure the deployed Render URL, not only localhost. CDN Brotli compression,
  Turso latency, the production Clerk domain, and B2 region all affect results.
- Verify a cold mock-exam start and material reader with network throttling.
  Large PDF/audio content should remain on-demand and support range requests.
- If the API is scaled horizontally, use a shared cache/rate-limit store and
  measure cache hit rate before increasing worker count.

## Reproduce the checks

```powershell
Push-Location frontend
npm ci
npm test
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
Pop-Location
```

In a second terminal, run Lighthouse against `http://127.0.0.1:4173/`, or use
Chrome DevTools Lighthouse/PageSpeed Insights against the deployed HTTPS URL.
Treat Performance, Accessibility, Best Practices, and SEO regressions as a
release review trigger rather than hiding them by increasing audit thresholds.
