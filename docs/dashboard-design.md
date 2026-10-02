# Unified Orbital Clarity interface

The recorded showcase and interactive local workbench share one application shell,
one semantic token sheet, and one background controller. This replaces the former
sidebar panel and separate workbench styling. The private design packet is excluded
from Git and build contexts; only necessary runtime assets and token definitions
are copied into the application.

## Navigation decision

Desktop reserves 184 px on the left for independent surfaced controls with icons
and visible labels. The rail itself is transparent: no continuous panel, enclosing
border, glass effect, or full-height background. Showcase and Workbench have small
section labels. Active destinations combine a 2 px Autumn Leaf marker with
`aria-current="page"`; selected context/background choices use `aria-pressed`.

Collapse/reopen, applicable Demo/Live choices, and background preferences live in
this system. Dataset, template, model, and run selections stay on their pages.
The showcase keeps its evidence journey and embedded evaluation regions.

Below 768 px, a sticky 44 px menu button and independently surfaced current-page
label replace the rail. Opening the menu focuses its first link and makes the
underlying content inert and visually hidden, leaving the backdrop visible between
controls. The menu scrolls within the viewport. Escape restores focus to the menu
button; selecting a destination closes it and returns focus. Views and background
remain mounted when switching areas, so navigation does not discard drafts,
selected records, filters, or runs. Page changes return to the top; collapsing
navigation does not reset the page or its state.

`#workbench` remains an alias for Datasets. Named workbench routes use
`#workbench/datasets`, `/classification`, `/runs`, `/results`, and `/connections`.
`#showcase` returns to the showcase. In-page anchors do not select another area.

## Foundations

| Role | Exact palette | Use |
| --- | --- | --- |
| Canvas | Graphite `#2C2C2C` | Shared backdrop and still/flat states |
| Surface | Gunmetal `#404040` | Floating controls, fields, selected reading surfaces |
| Context | Deep Space Blue `#28384E` | Active destinations and explanatory states |
| Accent | Autumn Leaf `#E86823` | Nontext active/error markers and chart marks |
| Text/boundary | Platinum `#EDF0F5` | Essential text, control boundaries, primary fills |

Essential text remains fully opaque. Primary actions have Platinum fills and
Gunmetal text; secondary actions have dark fills and Platinum boundaries.
Disabled buttons intentionally use 50% opacity to distinguish unavailable actions;
their explanations remain fully opaque. Disabled Signals describes the applicable
loading, source, empty-data, filter or live-calibration state.
Destructive actions retain an explicit action label and orange leading boundary.
Controls use 4 px radii; selected containers use 8 px; tables and rules remain
square. Metrics use open groups and selective dividers instead of repeated boxed
tiles. Editable sections use opaque surfaces where these improve interaction.

Spacing uses 4/8/12/16/24/32/48/64 px. Inter is self-hosted with optical size 14
and weights 400/500/600. IBM Plex Mono is self-hosted for technical identifiers.
Body is 16/24, labels 14/20, captions 12/18, headings 32/40 (28/36 narrow),
24/32 and 18/26, data 24/32, and identifiers 13/20. Upstream font licenses are
preserved in `LICENSES/Inter-OFL-1.1.txt` and `LICENSES/Plex-OFL-1.1.txt`.
Focus uses a 2 px Platinum outline with 2 px Gunmetal separation.

## Shared recipes and state boundaries

Fields, validation reports, topic editors, navigation, tables, metrics, pagination,
evidence, disclosures, status messages and charts use the shared recipes in
`apps/web/src/styles.css` and semantic tokens in `orbital-tokens.css`.
Scrollable tables have named, keyboard-focusable regions. Charts retain data
disclosures and coverage explanations. Missing dates, sparse coverage, partial
runs, locked workspaces and disabled runtime states remain explicit.
Single-choice selects use a shared 16 px Platinum chevron positioned 12 px from
the field edge, with 44 px of trailing text space. The native select semantics and
option menus remain intact; forced-color mode restores the native indicator.

Native application dialogs replace browser confirmation prompts for AI processing,
cancellation/resume, dataset deletion and original-text export. They describe the
action, focus Cancel first, contain keyboard focus while open, support Escape,
and return focus on completion. Existing privacy preview, consent checkboxes and
backend validation remain required; a cancelled dialog never submits the action.

Failed OAuth callbacks redirect to the configured local application with only
`connection=error`. Connections presents a fixed explanation and removes the flag
from the address. Codes, tokens, provider error descriptions and arbitrary return
destinations never enter this redirect. The failed authorization verdict and
existing state/nonce/identity/scope validation remain unchanged.

## Material and motion

The existing sand renderer mounts once in the shared shell, with intensity 1.25
and speed 0.85. Its module is bundled by Vite; the poster remains a local static
asset. Animate, Still and Flat are saved as nonsecret local preferences.
These three controls use a single icon row (Play, Pause and a solid square), with
accessible names, hover titles and programmatic pressed states. Destinations keep
their visible navigation labels. Animation restrictions are explained in the title
and background status text as well as through the disabled state.
Reduced-motion settings disable animation; unavailable graphics use the poster.
The renderer suspends when its document is hidden and destroys listeners and
graphics on unmount. The backdrop is decorative, `aria-hidden`, and
`pointer-events:none`. Foreground controls do not animate.

## Verification

Results and Showcase share an inspect-then-drill interaction: hover/focus previews
essential counts or rate denominators; click/Enter pins a scoped inspector, with an
explicit action to apply a period/category or inspect contributing records. The
desktop panel is nonmodal; the phone sheet uses a native dialog with focus return.
Tooltips stay within the viewport, and focused previews survive scroll/reflow.
Unknown time coverage remains a gap. Workbench volume charts aggregate UTC calendar
periods to at most 60 marks and retain their underlying daily disclosure. Showcase
rate charts preserve unavailable periods and never connect lines across gaps.

Wrapping action groups use 16 px gaps and 24 px top spacing, including run
configuration, connections, analysis, comparison and export actions. Native Results
menus use run-wide observed choices and explicit missing options. These additions
retain the shared floating rail, palette, motion and consent boundaries.

See the [v0.1.5 inspection review](quality/results-inspection-review.md) for the
latest evidence.

See the dated [browser and regression review](quality/orbital-ui-review.md) for
actual captures, exercised states, test results and remaining review limits.
Historical Figma captures and prior review reports remain historical evidence;
they are not the current implementation contract.
