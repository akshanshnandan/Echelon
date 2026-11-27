# Phase 12 performance and stability pass

## Method

`web/scripts/profile-command.mjs` drives a complete Ridge and Forest Command battle with B1, B2, and B3 attacking, at 4× simulation speed. It records every `requestAnimationFrame` interval from battle start to the visible result, plus Chromium DevTools trace events. Run from `web/` against the locally built FastAPI site, with `HEADFUL=1` for visible Chromium, `MOBILE=1` for 390×844, and `INTERACTIVE=1` for two selected units, camera zoom and pan. The interactive path checks the selection and camera change. The completed recording contains hit events. These are desktop Chromium viewport tests, not measurements on a phone.

Environment: Windows 11 Home 10.0.26200, Intel Core Ultra 7 155H (16 cores, 22 logical processors), Intel Arc graphics, 32 GB RAM, Playwright Chromium 159.0.8154.6, device scale factor 1. Headless and headful runs used the same local FastAPI process. The trace itself may add overhead. FPS is 1000 divided by mean frame interval; p95 is the 95th percentile of intervals. The result is a complete-battle sample, not the last 180-frame rolling metric exposed to the UI tests.

| Viewport and mode | Before FPS / p95 ms | After FPS / p95 ms |
| --- | ---: | ---: |
| 1440×900 headless | 35.4 / 66.8 | 48.6 / 49.9; repeat 46.6 / 33.3 |
| 1440×900 headful | 59.5 / 17.1 | 59.7 / 17.3 |
| 390×844 headless | 58.3 / 16.8* | 58.1 / 16.8 |
| 390×844 headful | 59.8 / 17.1* | 59.6 / 17.2 |
| 1440×900 headful, selected units and moved camera | — | 59.8 / 17.1; repeat 59.7 / 17.4 |
| 390×844 headful, selected units and moved camera | — | 59.8 / 17.1 |

*The two mobile before runs overlapped each other, so they are less controlled than the sequential after runs.

The earlier Phase 12 report recorded 24.1–37.6 FPS in five complete headless Playwright battles, with p95 83–133 ms. Its 60 FPS result came from a short, last-100-frame capture. The existing end-of-battle Playwright metric is a rolling 180-frame window, so it should not be read as whole-battle FPS. The 4× test also causes more simulation progress between 250 ms polls than ordinary 1× play. Run-to-run headless desktop variation remains significant; the apparent before/after increase is **not an attributable rendering improvement**.

## Trace findings

In the headful desktop before run, browser frame callbacks totaled 126 ms, layout 97 ms, and paint 266 ms across an 8.6-second battle. Maximum individual layout and paint events were 3.6 and 1.0 ms, and the browser reported no JavaScript long tasks. The headless desktop before run had no long tasks either; frame callbacks totaled 57 ms, layout 40 ms, and paint 167 ms across 7.1 seconds, with some individual paints up to 23.8 ms. The much larger headless desktop SVG viewport coincides with the lower frame rate. These measurements point to Chromium's headless rendering/compositing and test conditions, rather than a confirmed expensive React, JavaScript, network, or layout hot path. DevTools `RunTask` totals span threads and can overlap; they are not a main-thread percentage.

`CommandView.tsx` polls every 250 ms while the battle is live, and its interpolation writes formation transforms per animation frame. `CommandBattlefield.tsx` renders SVG terrain and formations. Poll responses change the authoritative tick and trigger expected UI updates. The trace did not justify a new renderer, changes to interpolation, or fewer live updates. The verified redundant work was polling while paused and after the battle ended. The viewer now stops those polls and stops repeated polls after a missing session. It also retains the latest hit effect for its full 650 ms when another effect arrives. The server, engine, game rules, AI, research environment, and replay encoding did not change.

## Stability and coverage

An expired Command session now shows a clear message and **New battle** action. Pause and speed controls are disabled after expiration or completion. Network failures still surface in the existing alert; setup uses a disabled button with a loading label, and the retry path remains available. Replay and download remain available after a finished battle while its session exists. Browser tests verify no polling after pause/completion and no repeated polling after a 404, plus drag selection, movement orders, zoom, pan, Classic and Expanded battles, Command replay, malformed replay rejection, and mobile layout.

These measurements support smooth headful playback on this laptop at the tested viewports, including the interactive case and hit events. They do not establish sustained 60 FPS on other GPUs, phones, or headless CI runners. Desktop headless performance remains variable and is the main open performance limitation before public promotion.
