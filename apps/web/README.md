# Feedback Intelligence web

React and TypeScript dashboard for Feedback Intelligence. The default presentation
context is the deterministic synthetic demo; the context control can switch to the
connected read-only API without mixing or caching data between the two.

The demo method control switches the descriptive dashboard between three complete
480-record sources: local SemIf, the deterministic rules baseline, and the Sol-medium AI
reference. Each exposes 15 monthly periods plus product, category, topic, language,
and channel filter states. The application uses the repository's Orbital Clarity
v0.4 foundation. Its Graphite fluid-sand
backdrop runs through the supplied WebGL 2 renderer at the approved 1.25× depth and
0.85× flow. A visible control pauses the material; reduced-motion preferences and
graphics failures use the supplied still poster. Gunmetal content surfaces keep text,
tables, and controls crisp above the moving backdrop.

The overview also loads a separate typed trend response. Demo mode shows the frozen
detector-only synthetic back-test with raw 7-day/current and 28-day/baseline counts,
alert episodes, and planted-incident outcomes. Live mode shows an unavailable state
until a calibrated policy can produce eligible analytical facts.

Demo overview also shows the measured 480-record SemIf-versus-Sol comparison. The
panel identifies Sol medium as an experimental AI reference, reports overall and
English/Swedish primary-topic agreement, and states that the results are not human
gold or calibrated production quality. It also labels the GPT-5.4 Mini experiment
as closed partial at 192/480, shows its subset quality, `$0.39` observed spend, and
the approximately `$0.98` full-run estimate alongside SemIf's zero API charge.
Live mode withholds this comparison while
human annotation is incomplete.

The time-series panel uses a fixed 0–100% scale, horizontal grid, average guide,
gradient area, smooth line, labeled monthly points, and latest/average/range summary.
The same values remain available in the disclosure table.

The implementation adapts a private Orbital Clarity design reference. All styles,
components, and required motion assets are included in `src/` and `public/orbital/`.
The original template is excluded from Git and Docker builds and is not needed to
build or run the application.

## Requirements

- Node.js 24.15.0 or newer
- npm 11.12.1 or newer

## Local development

```bash
npm ci
npm run dev
```

Vite serves the app at `http://localhost:5173` by default.
Requests below `/api` are proxied to `http://127.0.0.1:5080` during development.

## Quality checks

```bash
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
```

`npm run test` performs a single Vitest run. Use `npx vitest` when an interactive
watch session is useful during development.

## Container

Build from the repository root so the root `.dockerignore` and license files apply:

```bash
docker build -f apps/web/Dockerfile -t feedback-intelligence-web .
docker run --rm -p 127.0.0.1:8080:8080 feedback-intelligence-web
```

The container serves the production build on `http://localhost:8080`, proxies
`/api` to the Compose `api` service, and exposes a static health endpoint at
`http://localhost:8080/health`.
