# Repository audit — 9 October 2026

The audit preserved the existing uncommitted work and used isolated databases for all writes. The user's database was inspected read-only: one event and four routines, with no invalid schedules.

The subsequent [performance and logic audit](PERFORMANCE_LOGIC_AUDIT.md) records touchpad fixes, interaction measurements, additional functional fixes and current verification boundaries.

## Fixes

| Area | Finding and change |
| --- | --- |
| Window layout | A manual 1.35 density multiplier compounded Windows DPI scaling. Removed that multiplier, capped window sizes to the display, and separated tabs from calendar controls. Reserved space for sidebar actions and dialog save buttons. |
| Calendar | Header heights clipped day badges. Canvas titles wrapped outside their cards; unrelated events retained narrow overlap widths. Headers now fit, text is measured and shortened, overlap groups use independent widths, and dragging preserves duration near midnight. |
| Theme | Existing CTk widgets retained fixed colors, canvases used stale imported constants, and the light widget transparency key matched its background. Semantic light/dark pairs now cover CTk widgets, canvases redraw using the active palette, the transparency key stays distinct, and dropdown text has explicit contrast. |
| Settings | Focus, streak, week-start and notification preferences were stored but ignored. Consumers now apply them. Numeric settings are validated and saved in one transaction; dismissing appearance preview restores the prior theme. |
| Focus timer | Phase changes reacquired a non-reentrant lock; completion could join its own worker, and restart could leave an old worker running. Replaced the timer loop with interruptible, monotonic timing and safe transitions. Tk updates are queued to the UI thread. Skipped work does not earn completed focus minutes. |
| Persistence | UI and scheduler transactions shared an unprotected SQLite connection. Public database operations now serialize access. Mutations invalidate streak caches, an unfinished today preserves yesterday's streak, and deleted defaults are not reseeded on restart. |
| Undo/redo | Restored records received new IDs, updates omitted fields, checklist redo was incomplete, and failed actions consumed history. Snapshot restoration now preserves IDs and fields and changes records/history atomically. Event dialogs also record creation, editing and deletion. |
| Input | Invalid dates, time ranges, template durations and settings could be saved or silently defaulted. Shared validation rejects invalid records and dialogs show an actionable error. Fixed the undefined category list in the standalone template dialog. |
| Scheduling | Today's automatic suggestions could use past slots; exam revision fell back to a conflicting fixed time. Suggestions now use future slots, and unavailable revision slots produce a message. Reminders can fire before midnight for the following day's occurrence and deduplicate by that date. |
| Other UI | Restored search and documented Tasks/Focus shortcuts, kept checklist filters after refresh, synchronized widget checklist state, fixed future events being labeled NOW, and wrapped long task/widget titles. Charts redraw to their actual width and heatmaps include the previous year when needed. |
| Lifecycle | Hotkey/tray callbacks now queue to the Tk thread. Shutdown cancels recurring UI work, stops services, finishes focus sessions and closes SQLite, including startup failure paths. Canvas redraws release old tooltip/hover bindings. |
| Tooling | Added project lint configuration, core regression tests and a desktop UI smoke script. The launcher resolves its own directory and uses a local virtual environment. Dependency major versions are bounded where their APIs matter. |

## Verification

- Core regression suite: schedule validation, history identity and full snapshots, checklist metadata, history rollback on failure, concurrent database access, streak settings/cache, default seeding, notification preferences, midnight reminders, future scheduling, NLP examples and timer transitions/restarts.
- Desktop smoke: all six tabs, light/dark appearance, 900×600 and 1200×780 logical window sizes, four main dialog types and the desktop widget. Assertions check key controls, canvas appearance, and event text containment. The script also exercises theme cancellation, saved settings, checklist filtering and search.
- Screenshot inspection: calendar, tasks, focus, analytics, exams, routines and dialogs. Captures are generated under `artifacts/ui-audit/` and excluded from Git.
- Real application startup, scheduler initialization and shutdown with a temporary database. Native toast, global hotkey and tray adapters were mocked for this check; their operating-system integrations still need a manual end-to-end check.
- Python compilation and Ruff checks.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q core ui main.py config.py scripts tests
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe scripts/ui_smoke.py --capture
```

The GUI smoke script requires an interactive Windows desktop. Ruff is a development tool (`python -m pip install ruff`), not an application dependency. This audit does not claim exhaustive verification of every Windows configuration. Same-day event ranges and the existing 180-day streak history remain the supported behavior.
