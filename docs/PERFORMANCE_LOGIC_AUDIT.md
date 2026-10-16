# Performance and logic audit — 9 October 2026

Historical report: the [15 October product and engineering review](PRODUCT_ENGINEERING_REVIEW.md) supersedes the focus-accounting, streak and startup behavior described below.

This follow-up addresses interaction delays, touchpad scrolling, and functional correctness. Existing uncommitted changes were preserved. All write tests used memory or temporary databases; the user's schedule was not modified.

## Performance findings and fixes

- Calendar wheel handling truncated every delta below 120. Calendar canvases and scrollable lists/forms now retain fractional Windows wheel deltas and scroll in pixels. Scrollbars use the same handling. Scrolling cancels an active calendar scroll animation.
- Every tab change refreshed some views twice and rebuilt the calendar sidebar even when it was hidden. Only the active view now refreshes, with changes to the two affected tab buttons.
- Calendar headers, category controls, mini-calendar dates, task rows, countdown cards, routine lists and widget controls are retained when their data is unchanged. Height changes do not redraw the full time grid. Event fonts are reused and title truncation uses a binary search.
- Week, month and analytics reads queried each date separately. A range now expands daily, weekly, monthly and routine occurrences using one events query and one optional routines query. Bounded caches return independent snapshots and detect both local writes and writes from another app instance. Streak inputs are fetched in batches.
- Hidden analytics, task, exam and routine content loads when needed. Opening the main window and event dialogs no longer waits for a fade. Animations use elapsed wall time.
- The desktop widget updates task completion controls in place and retains unchanged schedule cards. Morning briefings and the widget generate the day's checklist before reading task statistics.

## Measured results

The same isolated fixture contains 780 events over 195 dates plus default routines. Interaction timings include Tk idle layout work and use the median of five repetitions. Startup is a single measurement. These are local measurements, not a guarantee for every machine. Round trips contain two tab changes; unchanged analytics measurements are warm cache hits.

| Operation | Before | After | SELECT queries before → after |
| --- | ---: | ---: | ---: |
| Create and display main window | 3,009 ms | 2,076 ms | — |
| Unchanged calendar refresh | 431 ms | 4.7 ms | 57 → 8 |
| Navigate one week | 430 ms | 54 ms | 57 → 10 |
| Tasks and back to Calendar | 805 ms | 190 ms | 1,215 → 11 |
| Analytics and back to Calendar | 705 ms | 200 ms | 357 → 8 |
| Unchanged analytics refresh | 176 ms | <0.1 ms | 229 → 0 |

## Logic fixes

- Checklist initialization uses a persisted per-date marker. Custom tasks no longer prevent initial schedule generation, and deleting generated tasks is respected on later visits. **Sync Schedule** explicitly restores missing scheduled tasks, updates linked titles/times without losing completion, removes obsolete pending generated tasks, and keeps completed and custom tasks.
- Checkbox persistence failures no longer leave a false completed state. Both the Tasks view and desktop widget record toggles in shared history; snapshot undo/redo preserves the exact task completion timestamp. Failed event moves do not create misleading history entries.
- Nested events no longer shorten continuous-busy-block warnings. Automatic scheduling can choose a preferred time inside a large free interval, rejects past dates, and preserves short Quick Add durations.
- Analytics **Focus Time** counts completed Pomodoro cycles rather than adding scheduled work to logged focus. **Today's Focus Score** uses the existing daily planning/completion algorithm instead of presenting scheduled category share as a concentration score. Recorded work without scheduled events receives credit. Weekly insights respect the saved first day of the week.
- Routine updates validate weekdays and active state. Empty exam titles and invalid manual task dates/titles are rejected. Malformed legacy event times cannot break streak calculations.
- Failed toast delivery leaves a reminder eligible for retry instead of marking it sent. Ending skipped cycles reports the number of work cycles actually completed.

## Verification and boundaries

- 30 unit regressions cover scheduling, recurrence across leap days/month boundaries, query batching, cache copy isolation and external writes, checklist generation/sync/history, validation, reminder retries, weekly preferences, focus scoring, timer transitions and wheel accumulation.
- Desktop smoke checks cover all six tabs at 900×600 and 1200×780 in dark and light appearance, four dialog types, settings, filters, search and the widget. Additional checks inject delta ±1 wheel events, verify pane routing and scrollbar scrolling, confirm closed dialogs release wheel bindings, and verify unchanged views retain their controls. No Tk callback errors were observed.
- Ruff and Python compilation pass. Screenshot captures are ignored under `artifacts/ui-audit/`.
- The real application starts its scheduler, creates both windows and shuts down cleanly in the isolated startup smoke check, with native toast/hotkey/tray adapters mocked.
- Physical laptop gestures and native toast/hotkey/tray integration require verification on the target hardware; the scrolling checks use real Tk with generated wheel events.
- Scheduled hours add event allocations, so overlapping events count separately. The configurable streak retains the existing 180-day planning/progress model: scheduled category minutes plus optional completed Pomodoro and checklist estimates. It is not a record of observed work. Pomodoro logging credits completed cycles; partial interrupted cycles remain unlogged. Recurring-event edits and moves affect the series; individual occurrence exceptions are not supported.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts/profile_ui.py
.\.venv\Scripts\python.exe scripts/profile_ui.py --profile
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/ui_smoke.py --capture
.\.venv\Scripts\python.exe scripts/startup_smoke.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m compileall -q core ui main.py config.py scripts tests
```
