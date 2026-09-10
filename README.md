# Timography

<p align="center">
  <strong>Intelligent Desktop Timetable, Calendar & Productivity Platform for Windows</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Platform-Windows%2011%20%7C%2010-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows 11">
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-blue?style=for-the-badge" alt="CustomTkinter">
  <img src="https://img.shields.io/badge/Storage-SQLite3-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Privacy-100%25%20Offline-brightgreen?style=for-the-badge" alt="100% Offline">
</p>

---

## 🌟 Overview

**Timography** is an all-in-one desktop productivity suite engineered specifically for students, developers, and knowledge workers. It combines a Google Calendar-inspired schedule planner with a floating frosted desktop widget, Raycast-style natural language event creation, an auto-scheduling gap finder, a daily task checklist, a Pomodoro focus timer, and rich time analytics.

Unlike web-based alternatives, Timography runs **100% locally and offline** with zero telemetry, zero latency, and persistent SQLite storage.

---

## ✨ Key Features

### 📅 Modern Google Calendar Layout & Fluid Drag-and-Drop
- **Interactive Day & Week Views**: Clean vertical hour grids with alternating row bands and subtle today-column tints.
- **Drag-and-Drop Rescheduling**: Click and drag any event block to reschedule; smoothly snaps to **15-minute intervals** vertically and shifts dates horizontally across columns.
- **Visual Ghost Preview**: A drop-shadowed translucent preview card tracks your cursor during moves.
- **Routine Lockout**: Recurring commitments (classes, gym, commutes) are visually distinct and locked against accidental moves.
- **Smooth Easing Animations**: Custom animation engine with ease-out cubic scrolling and alpha window fade-in transitions.

---

### ⚡ Natural Language Quick-Add (`Ctrl + Space`)
Summon a Spotlight / Raycast-style command bar from anywhere in Windows with a single keystroke:
- **Heuristic NLP Parsing**:
  - `"study math tomorrow 2pm for 90m"` → Schedules Math on tomorrow's date from 14:00 to 15:30 under *Study*.
  - `"team standup friday 10-11:30am"` → Adds a Work meeting from 10:00 to 11:30 on the upcoming Friday.
  - `"gym at 6pm for 1h"` → Auto-detects category *Health*, tags with red accent.
- **Live Visual Preview**: Instant real-time card preview showing detected title, date, time span, and colored category pills as you type.
- **Auto-Schedule Slot ⚡**: One click automatically relocates the event to your nearest open gap.

---

### 🧠 Smart Auto-Scheduler & Gap Recommendations
- **Free Slot Finder**: Analyzes overlapping busy intervals and finds open continuous windows across both regular events and recurring routines.
- **Circadian Category Matching**: Prioritizes afternoon and late-morning slots for deep study, business hours for work, and evening windows for workouts.
- **Fatigue Warnings & Gap Suggestions**:
  - Flags continuous blocks exceeding **3 hours** without rest breaks.
  - Highlights open **45–90 minute gaps** ideal for quick revision sessions or walks.

---

### ✓ Schedule-Based Daily Checklist
- **Automatic Morning Generation**: On startup, Timography populates a checkable daily to-do list synthesized from today's schedule and active routines.
- **Custom Tasks**: Add ad-hoc tasks anytime (`+ Add custom task...`).
- **Live Progress Metric**: Visual progress bar tracking completed tasks (`X / Y completed - Z%`).
- **Desktop Widget Sync**: Real-time checklist mini-progress bar mirrored directly on your desktop widget.

---

### ⏱️ Integrated Pomodoro Focus Timer
- **25 / 5 Focus Cycles**: Full-featured timer with work sprints, short breaks, and long breaks after 4 cycles.
- **Visual Cycle Progress**: Elegant visual indicators (`● ● ○ ○  Cycle 2 of 4`).
- **Desktop Toast Notifications**: Native Windows toast alerts fired at every phase change.
- **Productivity Logging**: Focused minutes are automatically logged to SQLite and integrated into your daily analytics.

---

### 📊 Time Analytics, Focus Score & Heatmap Dashboard
- **Category Donut Chart**: Visual breakdown of hours spent across Study, Work, Health, Social, and Routines.
- **Daily Hours Bar Chart**: Day-by-day comparison of scheduled vs. completed workload across the week.
- **Daily Focus Score (0–100)**: Proprietary scoring algorithm evaluating continuous focus blocks, context-switching penalties, checklist completion, and Pomodoro focus time.
- **Study Streak Tracker**: Calculates consecutive days with ≥30 minutes of study (`🔥 4-Day Streak`) and celebrates all-time best records.
- **28-Week GitHub-Style Activity Heatmap**: Interactive intensity grid plotting productive hours across the past 6 months with hover tooltips.

---

### 📚 Student Power Tools: Exam Countdowns & Templates
- **Urgency-Badged Countdowns**:
  - 🟢 **> 7 days**: Green status
  - 🟡 **3–7 days**: Yellow caution
  - 🔴 **< 3 days**: Red urgent warning
- **1-Click Study Revision**: Instantly auto-schedules a 90-minute study preparation session into the nearest open slot.
- **Event Templates**: Pre-configured templates (*Deep Work 90m*, *Study Session 2h*, *Gym 1h*, *Quick Review 30m*) for rapid one-click scheduling.

---

### 🪟 Frosted Glass Desktop Widget
- **Always-On-Top & Frameless**: 95% opacity frosted acrylic aesthetic with custom rounded corners.
- **Mini-Card Timeline**: Color-accented cards for upcoming tasks with a prominent **`NOW`** badge on active events.
- **Draggable Anywhere**: Position persistence across reboots.
- **Integrated Stats**: Displays today's study streak badge and checklist completion percentage.

---

### 🔔 Native Windows 11 Notifications & Scheduler
- **10-Minute Event Alerts**: Rich toasts with category, time, and notes before each event.
- **Daily Morning Briefing (07:30 AM)**: Daily digest summarizing event count, first meeting time, pending checklist items, and active streak.
- **Sunday Weekly Recap (08:00 PM)**: Comprehensive weekly debriefing of total scheduled hours and top category.
- **Streak Risk Warnings**: Reminds you before the day ends if your study streak is in jeopardy.

---

### ↩️ Full Undo & Redo Engine
- Accidental drag-and-drop? Deleted an event by mistake?
- Press **`Ctrl + Z`** to instantly restore; press **`Ctrl + Y`** to redo.
- Backed by an action log table preserving field snapshots.

---

## ⌨️ Keyboard Shortcuts Cheat Sheet

| Shortcut | Context | Action |
| :--- | :--- | :--- |
| **`Ctrl + Space`** | **Global (System-wide)** | Open Quick-Add command bar from any app |
| **`N`** | In-App | Open Create Event dialog |
| **`T`** | In-App | Jump to Today |
| **`D`** | In-App | Switch to Day view |
| **`W`** | In-App | Switch to Week view |
| **`C`** | In-App | Toggle Checklist to-do panel |
| **`P`** | In-App | Start Pomodoro focus timer |
| **`Ctrl + F`** | In-App | Focus event search bar |
| **`Ctrl + Z`** | In-App | Undo last event move / creation / delete |
| **`Ctrl + Y`** | In-App | Redo last undone action |
| **`Esc`** | Dialogs | Dismiss floating windows / Quick-Add |
| **`Enter`** | Quick-Add | Confirm and create parsed event |

---

## 📁 Project Architecture

```
Timography/
├── assets/                  # Icons and visual media
│   └── icon.ico             # Application icon
├── config.py                # Global settings, defaults, timings, and hotkeys
├── main.py                  # Application entry point, threading & tray orchestrator
├── requirements.txt         # Core dependencies
├── start.bat                # 1-click Windows launch script
│
├── core/                    # Headless business logic & background services
│   ├── analytics.py         # Focus score, weekly summaries, streak calculations
│   ├── auto_scheduler.py    # Free slot finder & intelligent gap recommendations
│   ├── database.py          # SQLite persistence layer (Events, Routines, Checklist, Pomodoro, Exams, Logs)
│   ├── hotkeys.py           # Global pynput listener & window shortcut binder
│   ├── nlp_parser.py        # Heuristic natural language date/time/title/category parser
│   ├── notifications.py     # Windows 11 toast notification manager
│   ├── pomodoro_engine.py   # State machine timer thread
│   ├── scheduler.py         # Background APScheduler cron jobs (briefing, recap, alerts)
│   └── undo_manager.py      # Action stack manager for undo/redo
│
└── ui/                      # CustomTkinter GUI presentation layer
    ├── animations.py        # Cubic easing curves, color lerp, smooth scrolling, fade-ins
    ├── analytics_dashboard.py# Canvas Donut & Bar charts, focus score gauge, streak stats
    ├── checklist_panel.py   # Daily to-do checklist panel with progress indicators
    ├── event_dialog.py      # Modal dialog for manual event addition/editing
    ├── exam_countdown.py    # Exam manager with urgency tags & revision scheduler
    ├── heatmap.py           # GitHub-style 28-week activity canvas grid
    ├── main_window.py       # Full Google Calendar-style desktop application
    ├── mini_calendar.py     # Month calendar widget with event dot indicators
    ├── pomodoro.py          # Fullscreen-capable Pomodoro focus window with cycle dots
    ├── quick_add.py         # Floating Spotlight/Raycast-style NLP quick-add bar
    ├── routines_dialog.py   # Recurring routine editor and presets manager
    ├── theme.py             # Color palettes, typography, shadows, and spacing constants
    ├── time_grid.py         # Canvas-rendered 24h schedule with drag-and-drop & shadows
    ├── tooltip.py           # Smooth fade-in dark floating tooltips
    ├── tray.py              # System tray icon with background controls
    └── widget.py            # Frosted glass always-on-top desktop schedule widget
```

---

## 🚀 Getting Started

### Prerequisites
- **Windows 10 or 11**
- **Python 3.10** or higher ([Download Python](https://www.python.org/downloads/))

### Installation

1. **Clone or Download the Repository**:
   ```bash
   git clone https://github.com/your-username/timography.git
   cd timography
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the Application**:
   ```bash
   python main.py
   ```
   *Or simply double-click `start.bat` on Windows.*

---

## ⚙️ Configuration (`config.py`)

You can customize defaults by editing [`config.py`](file:///d:/Timography/config.py):

```python
# Default reminder lead time
DEFAULT_REMINDER_MINUTES = 10

# Widget dimensions and position
DEFAULT_WIDGET_X = 50
DEFAULT_WIDGET_Y = 50
DEFAULT_WIDGET_WIDTH = 300
DEFAULT_WIDGET_HEIGHT = 460

# Pomodoro intervals (in minutes)
POMODORO_WORK_MINUTES = 25
POMODORO_SHORT_BREAK = 5
POMODORO_LONG_BREAK = 15
POMODORO_CYCLES_BEFORE_LONG = 4

# Global hotkey trigger
QUICK_ADD_HOTKEY = "<ctrl>+<space>"

# Minimum daily study minutes to maintain a streak
STREAK_MIN_STUDY_MINUTES = 30
```

---

## 🛡️ Privacy & Offline Guarantee

- **Zero Cloud Dependence**: Timography does not send your schedule, tasks, or study habits to any external servers.
- **Local SQLite Database**: All data is stored in `data/timography.db` on your local drive.
- **Lightweight & Fast**: Pure Python and native Windows APIs ensure minimal memory and CPU usage.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
