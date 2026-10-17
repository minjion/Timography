# Timography

A local Windows day planner for your schedule, tasks and focused work. No account or cloud sync is required. The app stores its data in SQLite and works offline after its dependencies are installed.

**New desktop overhaul:** run **start-next.bat** to try the Qt task-to-focus workflow. It uses a persistent independent copy of your planner; changes do not synchronize with the existing app. **start.bat** still opens the existing application. See [Timography Next](docs/TIMOGRAPHY_NEXT.md) for the implemented workflow, data handling and remaining migration work.

## Plan, work, review

- **Today** brings together your current/next event, agenda, task capture, completion progress and focus minutes. Start focus directly from an event or a pending task.
- **Calendar** provides day/week views, recurring events, category filters, search and drag-to-reschedule with 15-minute snapping.
- **Tasks** combines schedule-generated items and custom tasks, with completion filters and undo/redo. Deleted generated tasks stay deleted unless you explicitly choose **Sync Schedule**.
- **Focus** records active timer work, including partial sessions. Pauses and breaks do not earn minutes. Starting another task preserves an already-running session.
- **Insights** separates planned event allocations from timer work and shows progress toward your recorded-focus goal.
- **Exams and routines** retain countdowns, revision scheduling, repeatable weekly commitments and event templates.
- **Desktop widget** is available from the tray. Settings can make it the only window shown on launch.

New databases include editable routine and template examples. Existing events, routines, tasks and history are preserved during upgrade.

## Launch

Windows 10/11 and Python 3.10 or newer are required. From this project folder, double-click **start.bat**. It creates a local virtual environment and installs missing dependencies. The main planner opens to Today.

For manual setup:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```


Closing the planner hides it. Use the tray menu to reopen the planner, toggle the widget or quit. Reminders and the global Quick Add shortcut require the app to remain running. A process lock prevents a second copy from opening the same database.

## What the numbers mean

| Metric | Meaning |
| --- | --- |
| Scheduled hours | Event allocations in the selected period. Future blocks count; overlapping allocations are added separately. |
| Focus time | Measured active work from new timer sessions. Historical sessions retain their original completed-cycle estimates. |
| Today's focus goal | Timer minutes in your selected categories divided by the saved daily goal, capped at 100%. |
| Focus goal streak | Consecutive days meeting that recorded-focus goal. An unfinished today preserves yesterday's streak; the best streak includes available recorded history. |
| Tasks completed | Actual task checkmarks. They add no artificial focus minutes and are not completed automatically when a timer ends. |

Measured sessions save checkpoints every five seconds and on pause, skip, reset and normal shutdown. A crash or forced termination can lose work since the last successful checkpoint, normally about five seconds with healthy storage. Recovery closes interrupted sessions without inventing time while the app was closed.

## Data, backups and recovery

The working database is **data/timography.db** in this project folder. Settings shows its full location.

- Before changing an existing database on startup, the app creates a validated SQLite snapshot. It keeps the seven most recent automatic snapshots in **data/backups/**.
- **Settings → Data & Recovery → Back up data** exports a separate snapshot, including saved settings and undo history.
- **Restore backup** validates the file, finishes any active focus session, stops background services, makes a safety snapshot, restores and restarts the app. Current data is retained if restoration fails.
- Unreadable automatic snapshots are retained under a name containing **corrupt** and replaced with a fresh snapshot from the working database.
- Diagnostic logs rotate under **data/logs/**. Native notification failures are visible in the planner's status bar.

Copy an exported backup when moving to another computer. Do not rely on copying an active SQLite file: an active database can also have journal/WAL sidecar files.

## Keyboard shortcuts

Shortcuts apply when you are not typing into a text field.

| Shortcut | Action |
| --- | --- |
| Ctrl+Space | Global Quick Add |
| 1 / 2 / 3 | Calendar / Tasks / Focus |
| 4 / 5 / 6 | Insights / Exams / Routines |
| 7 | Today |
| N | New event |
| T | Go to today's date |
| D / W | Calendar day/week view |
| C / P | Tasks / Open Focus, starting a session if idle |
| Ctrl+F | Calendar search |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| Escape | Close a dialog |

Quick Add understands expressions such as **study math tomorrow 2pm for 90m** and **gym at 6pm for 1h**. Its preview shows the interpreted date/time before creation. It is a local rule-based parser; review ambiguous input.

Recurring-event edits and moves affect the series. Individual occurrence exceptions and overnight events are not currently supported.

## Verification

All writable tests use memory or temporary databases. Desktop checks require an interactive Windows session.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/startup_smoke.py
.\.venv\Scripts\python.exe scripts/ui_smoke.py --capture
.\.venv\Scripts\python.exe scripts/release_ui_smoke.py --capture
.\.venv\Scripts\python.exe scripts/lifecycle_ui_smoke.py
.\.venv\Scripts\python.exe scripts/profile_ui.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m compileall -q core ui main.py config.py scripts tests
```


Ruff is a development tool and is not required to launch the app. Native toast, tray, global hotkey behavior and physical touchpad gestures still require a manual check on the target machine.

See the [product and engineering review](docs/PRODUCT_ENGINEERING_REVIEW.md), [original audit](docs/AUDIT.md), and [earlier performance audit](docs/PERFORMANCE_LOGIC_AUDIT.md). The latest review supersedes the earlier audit's completed-cycle-only logging and planning-streak definitions.
