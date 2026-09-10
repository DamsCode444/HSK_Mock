# HSK Mock Test Platform

Practice Chinese with realistic HSK mock exams, a study library, and a personal
progress dashboard.

[Visit the live website](https://hsk-mock-1.onrender.com/)

## Explore the website

- [Mock exams](https://hsk-mock-1.onrender.com/) — browse available HSK tests.
- [Study library](https://hsk-mock-1.onrender.com/materials) — read course books
  and listen to matching lesson audio.
- [Vocabulary library](https://hsk-mock-1.onrender.com/materials?edition=vocabulary)
  — study vocabulary resources covering Levels 1–6 and the combined 7–9 range.

Create an account or sign in to take exams, access study resources, and track
your learning.

## Features

### Realistic mock exams

- HSK 1–6 practice with listening, reading, and writing sections.
- Timed sessions, fullscreen mode, and clear section progress.
- Question navigation with answered and unanswered indicators.
- Readable question content and a zoomable source-page viewer.
- Keyboard shortcuts and controls designed for desktop, tablet, and mobile.
- Answer autosave, recoverable drafts, and resume support.
- Warnings before leaving and confirmation before submitting.
- Section scores, results, and answer review after submission.

### Study materials

- HSK 2.0 and HSK 3.0 resources organized by level and book.
- Textbooks, workbooks, and vocabulary PDFs where available.
- Integrated document reader and book cover previews.
- Lesson-grouped audio with seeking, playback speed, and next-track playback.
- Downloads for individual books, audio tracks, and available study bundles.
- Resource availability depends on the supplied content; vocabulary-only books
  do not include invented audio.

### Student dashboard

- Test history and score trends.
- Section performance and weak-area analysis.
- HSK level roadmap and recommended practice.
- Progress indicators, loading states, and clear empty states.

### Administration

- Overview statistics and searchable management screens.
- Exam import, publication, archival, and settings.
- User roles and account status management.

### Design and accessibility

- Consistent typography, spacing, colors, and responsive layouts.
- Smooth page transitions, chart animations, and score reveals.
- Visible keyboard focus and reduced-motion support.
- Toast notifications, confirmation dialogs, and skeleton loading.

## How to get started

1. Open the [website](https://hsk-mock-1.onrender.com/) and sign in.
2. Choose an HSK level and an available mock test.
3. Complete the exam and review your results.
4. Use your dashboard to identify areas for practice.
5. Open the study library for related books and lesson audio.

## Built with

- Vue 3, Vite, Pinia, Vue Router, Element Plus, and Tailwind CSS.
- Python, FastAPI, and SQLAlchemy.
- Clerk authentication.
- pytest and Node's built-in test runner.

## Validation

The latest local verification on September 10, 2026 recorded:

| Check | Result |
| --- | --- |
| Backend tests | 105 passed |
| Frontend tests | 3 passed |
| Frontend production build | Passed |
| Production frontend dependency audit | 0 reported vulnerabilities |
| Lighthouse performance | 93 |
| Lighthouse accessibility | 100 |
| Lighthouse SEO | 100 |

Lighthouse scores were measured against a local production preview and may
differ on the live deployment. Best Practices scored 79 because of
third-party development authentication cookies. See the
[performance report](docs/PERFORMANCE_REPORT.md) for measurement conditions.

## Repository and content

This repository contains application source code. Private configuration,
credentials, database exports, source books, exam bundles, and generated media
are excluded from version control.

Study content belongs to its respective owners. Availability on the website
does not grant redistribution rights. Obtain permission before reusing or
distributing books, audio, or exam materials.

## License

No open-source license has been granted for this repository. Copyright remains
with the respective code and content owners.
