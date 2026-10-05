# Model controls, documentation and preview review — 2026-10-02

Checkpoint: `v0.1.6`, on the existing draft Workbench branch. The v0.1.0 source
release and frozen model comparison artifacts remain unchanged.

## Implemented and verified

The README and public walkthrough now describe the recorded Showcase and executable
local Workbench separately. Capability/availability tables, architecture, privacy,
model limitations, release readiness and synthetic screenshots reflect the current
workflow. The historical GIF remains explicitly historical. The architecture SVG
was rendered and inspected; Workbench Results correctly read PostgreSQL rather than
pretending the UI reads its analytical projection directly.

Connections and Classification share one account-scoped catalog loader. Visible
views refresh every five minutes, on entry/connection changes, and on window focus
when older than one minute. Manual refresh is available. Catalog order is retained;
future account-listed models remain discoverable. Failed refreshes mark old choices
stale and block new AI runs. Removed models require an explicit selection; withdrawn
effort settings also require another choice rather than a silent replacement.

The additive models response exposes supported efforts and their source. Provider
metadata takes precedence; documented GPT-6/GPT-6.1 and GPT-5.4 Mini/nano profiles
were reviewed against official OpenAI documentation on 2026-10-02. Unknown models
use Provider default, without inventing effort capabilities. The server validates
availability/effort before creating a run. Explicit effort enters the Responses
request and immutable run/result provenance; sample reuse requires a match.
Existing snapshots are not rewritten. No database migration was added.

Chart previews use pointer coordinates or the selected SVG point transformed into
viewport coordinates, with measured flipping/clamping. Native pointer movement in
the browser produced a preview at left 912/top 412 for a pointer at 900/400, instead
of anchoring at the chart container's lower-left corner. Keyboard navigation,
Escape, pinned inspection and focus return remain intact.

Related browser-discovered repairs prevent selecting active Signals from clearing
loaded evidence indefinitely, and contain positioned screen-reader table labels
inside their scroll region rather than widening the phone document.

## Browser evidence

The Codex in-app browser exercised current React code with deterministic fixture
clients and the rebuilt recorded Docker demo. No external inference or sign-in was
initiated. Overview, Signal and Workbench chart previews and model/effort settings were checked at 1440,
1024, 768, 390 and 320 CSS px; document width matched the viewport after repairs.
Tooltips stayed within margins. One decorative canvas remained mounted.

The account/model/High-effort selection survived Classification → Connections →
Classification. GPT-6.1 Sol offered Provider default, Low, Medium, High, Extra high
and Max, without unsupported None/Minimal choices. The sample action remained
blocked without external-processing consent. Workbench chart periods and pinned
inspection were also exercised with the 10,000-record/450-date fixture.

Public captures under `docs/assets/` use actual recorded synthetic SemIf data for
Showcase, evidence, comparison and phone views. Workbench Results/settings captures
use deterministic synthetic fixtures and a clearly labeled mock catalog. Ignored
additional captures are under `artifacts/model-controls/`.

Limits: one browser surface, not a cross-browser, screen-reader or real-touch
certification. The earlier native 200% zoom limitation remains; no new native zoom
or operating-system reduced-motion certification is claimed. Mock catalog/stream
checks do not establish real provider admission or quality of newly available models.

## Automated and local runtime checks

- Frontend format, lint, types, 104 tests and production build passed, including
  pointer anchors, catalog refresh/races, withdrawn selections, explicit effort
  approval and repeated active Signals navigation.
- API formatting and Release build passed; 62 tests passed and one optional
  PostgreSQL integration test was skipped. Capability profiles, metadata precedence,
  unknown models and unsupported effort validation use no paid calls.
- Worker lint/format/types and 143 tests passed. Streaming tests verify effort
  transmission, default omission, terminal completion, privacy and recorded settings.
- Real isolated Workbench storage verified lease/fencing protections, immutable
  decisions, role separation, effort persistence on resume, idempotency rejection
  after changed effort, rejection of mismatched-effort sample reuse, and same-effort
  expansion. AI decisions in this check are synthetic mocks; no inference occurs.
- Rebuilt local upload → validation → rules → evidence → export → durable purge
  acceptance passed using disposable fixtures.
- All 22 contract schemas, frozen predictions/reports, generated public benchmark,
  seven publication regressions and publication path inventory passed.

Remote CI evidence is linked from the updated draft PR. Real-account classification
verification remains pending by the owner's documentation choice. Hosted operation,
human calibration and release promotion remain independent acceptance gates.

## Authentication recovery — v0.1.7, 2026-10-05

The live local picker failure was traced to HTTP 400 `invalid_grant` during
ChatGPT token renewal, before the model catalog request or inference. The app now
returns a safe recovery code/message, offers a direct path to the existing account's
Reconnect control, and records a terminal reconnect requirement. Unusable tokens
are cleared while the issued client ID and account identity are retained. Temporary
failures preserve tokens; API billing is never selected automatically.

Mock regressions cover terminal vs temporary failures, no provider-description
canary in diagnostics, no repeated renewal of invalid tokens, saved-registration
reuse, successful reauthorization, and disabled processing with the reconnect path.
Restoring this particular live catalog requires owner-completed reconnection; no
classification request was made during diagnosis.

Checkpoint checks: frontend format/lint/types/build and 105 tests pass; API format/Release build and 64 tests pass (one optional database test skipped); 143 worker tests pass. Frozen benchmark and publication checks remain unchanged.
