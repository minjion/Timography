# Timography Next — first overhaul milestone

17 October 2026

This milestone implements the proposed task-to-focus vertical slice in a new Qt Quick desktop interface. It is an executable workflow backed by the shared Python core and SQLite store. The existing application remains available while the new interface is evaluated; this is not a feature-complete replacement for all seven legacy tabs.

## Run it

Double-click **start-next.bat** in the project folder. It installs the optional Qt dependencies into the existing virtual environment when needed, then opens the new interface. **start.bat** continues to open the existing application.

Manual launch:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-next.txt
.\.venv\Scripts\python.exe main_qt.py
```

On its first launch, Next snapshots the existing `data/timography.db` into `data/preview/timography.db` through SQLite's backup API. This includes committed WAL contents without upgrading the source database. If no source database exists, Next initializes a new preview database. Later launches reuse the preview, retaining your work. The source is not recopied over your preview.

**The two planners do not synchronize.** Changes made in Next affect the preview only. The interface identifies this mode and shows its database location. Preview snapshots and logs live beside the preview database.

For an explicit disposable database:

```powershell
.\.venv\Scripts\python.exe main_qt.py --database C:\Temp\timography-evaluation.db
```

`--database` opens that file directly and creates an automatic backup before migration. `--preview-database` changes the location of the independent preview copy. Both modes use the database process lock, preventing two applications from opening the same store concurrently.

## The implemented journey

1. Capture an unscheduled task with a category and estimated duration.
2. Edit its title, notes, category or estimate without replacing its identity.
3. Add one or more same-day calendar blocks. Overlap warnings are advisory; estimates do not invent recorded work.
4. Start the task's focus session. Pause/resume and end the session while retaining partial active work; starting a different task preserves the active session.
5. Complete the task. Completing an active task saves and ends its focus session first. Timer completion alone never checks the task off.
6. Review recorded time and recent sessions. Historical completed-cycle estimates remain distinguishable from newly measured work.

Light/dark appearance is persisted. Native Qt scrolling, keyboard focus and adaptive layouts replace the custom Tk scrolling/layout code in this interface. Backup export uses the validated SQLite snapshot mechanism. Closing the window saves the active session; an unsuccessful final save keeps normal window closure from proceeding so it can be retried.

## Shared architecture

`TaskService` owns task capture, editing, scheduling, completion, deletion and focus association. The Qt adapter translates these operations into properties and signals; it does not contain task SQL. `PomodoroEngine` remains responsible for measured active work, checkpoint retries, pauses, breaks and midnight splits.

The migration is additive and versioned. Existing `checklist_items.id` values remain the canonical task IDs, preserving legacy completion metadata and undo snapshots. New task details, calendar block links and focus-session links are stored separately. Multiple blocks can belong to one task; legacy checklist generation skips those calendar entries rather than generating another task for each block.

Service-created calendar entries belong to their task and can be removed with a block. Imported legacy events and recurring series are retained when a task is detached or deleted. Detaching a legacy block removes its task association; it does **not** cancel the original calendar occurrence. This distinction is surfaced in the interface.

Focus history and its daily ledger survive task deletion. Migration links legacy sessions only where occurrence attribution is unambiguous. Full focus accounting and the pre-existing backup/recovery safeguards remain shared with the old application.

## Evaluation and remaining work

The first milestone is intended to establish a tested foundation and evaluate the new interaction model. It does not yet port the weekly calendar editor, recurring-series editing, occurrence exceptions, overnight blocks, exams, routine/template editing, global hotkeys, reminders, tray or desktop widget into Qt. Undo/redo in the new task workflow and a user-facing restore/restart flow also remain work for the replacement release; the legacy application retains its own existing features.

Next steps are to evaluate this complete journey on the target laptop, extend the calendar/recurrence model behind shared services, port the remaining screens, then produce and verify an installer and data-location migration. The framework change alone does not establish faster interaction or better accessibility; real measurements and keyboard/touchpad checks are needed alongside the automated coverage.

The Qt implementation follows the official [Python/QML application integration](https://doc.qt.io/qtforpython-6/tutorials/qmlapp/qmlapplication.html). Future standalone packaging can use the official [Qt for Python deployment tooling](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html).

## Verify locally

All writable fixtures use temporary or in-memory databases.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/qt_smoke.py
.\.venv\Scripts\python.exe scripts/qt_startup_smoke.py
.\.venv\Scripts\python.exe scripts/startup_smoke.py
.\.venv\Scripts\python.exe scripts/ui_smoke.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m compileall -q core ui desktop_qt main.py main_qt.py scripts tests
.\.venv\Scripts\python.exe -m pip check
```

The Windows CI workflow runs core/controller tests, Qt interface checks, lint, compilation and dependency consistency checks. Its configuration is included in the repository; hosted execution is not implied by a local test pass.

Local verification for this milestone passed **94 unit/integration tests**, **16 Qt page/theme/size combinations**, and the existing **28 legacy view/theme/size combinations**. Real Qt pointer journeys cover capture, invalid/valid scheduling, editing, pause/resume, partial-session completion and review. Injected write failures verify checkmark rollback and a retriable window close; a twelve-block scheduling dialog retains reachable actions at the minimum window size. Pixel-only wheel events and refreshes preserve task-list scrolling. The Qt run reports no QML warnings or Python callback exceptions.

Separate-process startup checks cover a first preview snapshot, reuse of an edited preview, direct database mode, duplicate-instance exclusion and partial focus flushed by closing the actual window. The old application's startup/recovery/restore checks also pass. Qt smoke checks run both with the normal Windows backend and the software/offscreen configuration used by CI. Physical touchpad gestures still need verification on the target laptop; injected pixel events exercise the application path rather than its hardware driver.
