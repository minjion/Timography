# Product and engineering review — 15 October 2026

The team chose a substantial improvement of the existing desktop application. The work covers the daily workflow, timer/accounting model, data recovery, interaction stability and independent QA. Existing uncommitted work was preserved; all writable fixtures used temporary or in-memory databases.

## Direction

The previous performance work provided a useful foundation: a local SQLite store, separate business logic and views, and regression coverage. Replacing the UI framework would add migration and platform risk without fixing the missing daily workflow. The revised experience connects planning, task capture, focused work and review in the existing Windows app.

The product position is a dependable local day planner with no account requirement. This is a recommendation based on a desk review of official product materials, not a claim of validated customer demand.

- [Sunsama timeboxing](https://www.sunsama.com/features/timeboxing) and [daily planning](https://help.sunsama.com/docs/usage-guides/daily-planning/) connect task selection with time allocation. The implication here is to improve the daily flow rather than add more disconnected tools.
- [TickTick's official feature list](https://ticktick.com/features?language=en_us) already includes calendar, task and focus capabilities. Reliable offline interaction is a more useful distinction than a larger feature checklist.
- [Structured's focus timer](https://help.structured.app/en/articles/331010) connects a timer to the work in view. Timography now starts focus from a pending task or the current/next event.
- [Windows Focus](https://support.microsoft.com/en-us/windows/experience/focus-stay-on-task-without-distractions-in-windows) includes OS-level distraction controls. Timography does not claim to suppress operating-system notifications; its value is connecting the planner and work record.

## Delivered behavior

| Area | Change | User benefit |
| --- | --- | --- |
| Entry point | The planner opens to Today; widget-only startup is an explicit preference. The main-mode widget starts hidden and remains available from the tray. | A visible, predictable start to the app. |
| Today | Current/next event, agenda, task capture, completion progress and focus actions share one page. | Move from a plan to an action without navigating several tools. |
| Contextual focus | Pending tasks and events prefill the focus title/category and appropriate event link. Existing active sessions are preserved. Editing an idle target clears a stale event association. | Less repeated entry and correct work attribution. |
| Focus accounting | New sessions measure elapsed active work, include partial cycles, exclude pauses/breaks and split at midnight. Cumulative checkpoints are idempotent and retry failed saves. | Interrupted sessions still earn their actual work time. |
| Goal semantics | Goal progress and streaks use timer work in selected categories. Plans and arbitrary per-task estimates do not create completed minutes. Historical completed-cycle estimates remain available. | Planned and completed work have distinct meanings. |
| Recovery | Startup closes interrupted measured sessions using their last saved checkpoint. A process lock prevents a second app from recovering a timer still running in the first app. | No fabricated credit while the app was closed. |
| Backups | Validated SQLite snapshots before startup migration, seven automatic snapshots retained, manual export and safe restore/restart with a pre-restore safety snapshot. | Recover data without manually copying a live SQLite file. |
| Failures | Storage/native-notification failures surface in the status area; diagnostics rotate locally. Restore failures retain current data, and startup failures return a failure exit code. | Problems have actionable feedback instead of silently disappearing. |
| Layout/input | Restrained navigation, light/dark contrast, logical-pixel wrapping and precision wheel accumulation across scrollable views. | Better laptop interaction and readable long titles. |

## Important engineering findings

The UI pass reproduced a genuine freeze with long task titles. Hidden views were sizing wrapped text against their own requested width; the resulting geometry feedback loop was amplified by CustomTkinter's scrollbar calling nested idle processing. Visible-ancestor guards, deferred sizing and an app-owned stable scrollbar resolve the failing flow without patching installed dependencies.

Real pointer clicks also exposed delayed button animations running after their dialog or task row was destroyed. App-owned controls now cancel their own pending callbacks before destruction and release each popup's global focus binding. The regression checks capture Tcl background errors as well as Python callback exceptions; direct method invocation alone had missed this failure.

SQLite backup uses the connection backup API, including committed WAL content. Exports are built and validated in a temporary file before replacing an existing export. Restore checks database integrity and the required application schema, including the optional focus ledger, retains a safety snapshot, and rolls back if additive migration fails. Corrupted automatic snapshots are retained for diagnosis and regenerated from the healthy working database.

The focus migration adds a nullable measured-seconds column and per-day ledger. Null legacy values retain their completed-cycle estimates; they are not rewritten as if historical elapsed time had been measured. The old planning-based streak preference is migrated to the recorded-focus model once. Existing schedules, custom settings, history identifiers and completed task metadata remain intact.

## Verification

- **58 unit/integration tests:** validation, recurring expansion, history, multithreaded access, measured focus and midnight splits, checkpoint retries, legacy migration, streaks, WAL snapshots, restore rollback, schema rejection, automatic retention and cross-process exclusion.
- **28 view combinations:** seven tabs, both themes, 900×600 and 1200×780 logical sizes. Tests inspect action bounds and actual rendered text containment at 125% DPI.
- **Release journeys:** task capture/completion/history, respected deletion, actual task/event/routine focus association, active-session preservation, manual source editing, precision wheel routing, widget transitions, settings workers, cancellation and preview rollback.
- **Application lifecycle:** planner and widget launch modes; dialogs available in widget mode; interrupted-session recovery; active focus flushed before restore safety backup; actual restored contents; restart request; duplicate-instance handling; scheduler startup/shutdown. Each case runs with temporary data and a fresh interpreter.
- **Real click lifecycle:** Save/Create/Delete actions, task-row removal and immediate popup closure produce no Python or Tcl background errors. Repeated popup closure preserves global binding counts.
- **Static checks:** Ruff, Python compilation, dependency consistency and whitespace checks.

The final local profiler used 780 event records in an isolated database and five samples per interaction, including Tk event processing. Median calendar refresh was **4.5 ms**, week navigation **63.6 ms**, Tasks/Calendar round trip **297.4 ms**, and Insights/Calendar round trip **293.8 ms**. Initial window construction and first render took **1.90 seconds**. These are local measurements, not performance guarantees or full process-startup timings; round trips include two tab switches. Unchanged Insights refresh used its cache with no SELECT queries.

Application-only screenshots are generated under `artifacts/ui-audit/` and excluded from Git. Source changes remain reviewable in the working tree.

## Boundaries

Physical touchpad gestures and native tray/hotkey/toast delivery still need an end-to-end check on the target machine; tests use real Tk controls with injected events and mocked native adapters. Focus recovery uses the last successful checkpoint, normally saved every five seconds. Storage failures or forced termination can leave later work unpersisted.

Scheduled hours add allocations, so overlaps count separately. Individual recurrence exceptions, overnight events, cloud sync, OS distraction suppression and an installer are outside this revision. Recurring edits and moves apply to the series; the editor makes that scope explicit. No claim of exhaustive defect elimination or accessibility certification is made.

## Reproduce

Run from the project folder on Windows:

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

Earlier audits record the prior behavior and measurements. This review supersedes their completed-cycle-only focus accounting and planning/progress streak definitions.
