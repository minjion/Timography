import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "."

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    width: 1280
    height: 840
    minimumWidth: 800
    minimumHeight: 600
    visible: true
    title: "Timography Next"
    color: Theme.background
    font.family: Theme.family
    font.pixelSize: 14
    palette.window: Theme.surface
    palette.windowText: Theme.text
    palette.base: Theme.background
    palette.text: Theme.text
    palette.button: Theme.raised
    palette.buttonText: Theme.text
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.accentText
    palette.light: Theme.border
    palette.mid: Theme.border
    palette.dark: Theme.border
    property int page: 0
    property string taskFilter: "Open"
    readonly property var openTasks: planner.tasks.filter(function(task) { return !task.is_completed })
    readonly property var displayedTasks: planner.tasks.filter(function(task) {
        return taskFilter === "All" || (taskFilter === "Done" ? task.is_completed : !task.is_completed)
    })
    readonly property var activeTask: planner.tasks.find(function(task) { return task.id === planner.activeTaskId })

    onClosing: function(close) { close.accepted = planner.requestClose() }

    function startTask(id) {
        if (planner.startFocus(id)) page = 2
    }
    function openSchedule(task) {
        planner.clearError()
        scheduleDialog.task = task
        var start = new Date()
        start.setMinutes(Math.ceil((start.getMinutes() + 1) / 15) * 15, 0, 0)
        var end = new Date(start.getTime() + task.estimate_minutes * 60000)
        if (end.getDate() !== start.getDate()) {
            start.setDate(start.getDate() + 1)
            start.setHours(9, 0, 0, 0)
            end = new Date(start.getTime() + task.estimate_minutes * 60000)
        }
        scheduleDate.text = Qt.formatDate(start, "yyyy-MM-dd")
        scheduleStart.text = Qt.formatTime(start, "HH:mm")
        scheduleEnd.text = Qt.formatTime(end, "HH:mm")
        scheduleDialog.open()
        scheduleDate.forceActiveFocus()
    }
    function openEdit(task) {
        planner.clearError()
        editDialog.task = task
        editTitle.text = task.title
        editCategory.currentIndex = Math.max(0, editCategory.find(task.category))
        editNotes.text = task.notes || ""
        editEstimate.value = task.estimate_minutes
        editDialog.open()
        editTitle.forceActiveFocus()
    }

    Shortcut { sequence: "Ctrl+1"; onActivated: window.page = 0 }
    Shortcut { sequence: "Ctrl+2"; onActivated: window.page = 1 }
    Shortcut { sequence: "Ctrl+3"; onActivated: window.page = 2 }
    Shortcut { sequence: "Ctrl+4"; onActivated: window.page = 3 }
    Shortcut { sequence: "Ctrl+N"; onActivated: { window.page = 0; captureFocus.focusTitle() } }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: window.width < 1000 ? 160 : 186
            Layout.fillHeight: true
            color: Theme.surface
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 8
                Label {
                    text: "Timography"
                    color: Theme.text
                    font.pixelSize: 21
                    font.weight: Font.Bold
                    Layout.topMargin: 16
                }
                Label { text: "A calmer working day"; color: Theme.muted; font.pixelSize: 11; Layout.bottomMargin: 32 }
                Repeater {
                    model: [{title: "Today", name: "navToday"}, {title: "Tasks", name: "navTasks"}, {title: "Focus", name: "navFocus"}, {title: "Review", name: "navReview"}]
                    delegate: AppButton {
                        required property var modelData
                        required property int index
                        objectName: modelData.name
                        Layout.fillWidth: true
                        text: modelData.title
                        tone: window.page === index ? "primary" : "quiet"
                        onClicked: window.page = index
                        Accessible.description: "Control " + (index + 1)
                    }
                }
                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                Label { text: planner.previewMode ? "Preview workspace" : "Your workspace"; color: Theme.muted; font.pixelSize: 11; Layout.topMargin: 12 }
                AppButton {
                    objectName: "themeToggle"
                    Layout.fillWidth: true
                    text: Theme.dark ? "Light appearance" : "Dark appearance"
                    compact: true
                    tone: "quiet"
                    onClicked: planner.setDarkMode(!planner.darkMode)
                }
            }
        }
        Rectangle { width: 1; Layout.fillHeight: true; color: Theme.border }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: window.width < 1000 ? 20 : 30
            spacing: 16

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: previewLabel.implicitHeight + 24
                visible: planner.previewMode
                color: Theme.accentSoft
                radius: 10
                Label {
                    id: previewLabel
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    text: "PREVIEW COPY  ·  Changes stay in this workspace and do not sync back to your current planner."
                    color: Theme.accent
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
            }
            Rectangle {
                objectName: "errorBanner"
                Layout.fillWidth: true
                implicitHeight: Math.max(42, errorLabel.implicitHeight + 24)
                visible: planner.errorMessage.length > 0
                color: Theme.dangerSoft
                radius: 10
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    Label {
                        id: errorLabel
                        Layout.fillWidth: true
                        text: planner.errorMessage
                        color: Theme.danger
                        wrapMode: Text.Wrap
                        Accessible.role: Accessible.AlertMessage
                    }
                    AppButton { text: "Dismiss"; compact: true; tone: "quiet"; onClicked: planner.clearError() }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: window.page

                ScrollView {
                    id: todayScroll
                    objectName: "todayScroll"
                    clip: true
                    contentWidth: availableWidth
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    PrecisionWheel { flickable: todayScroll.contentItem }
                    ColumnLayout {
                        width: todayScroll.availableWidth
                        spacing: 20
                        RowLayout {
                            Layout.fillWidth: true
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 5
                                Label { text: "Today"; color: Theme.text; font.pixelSize: 30; font.weight: Font.Bold }
                                Label { text: planner.dateLabel; color: Theme.muted; font.pixelSize: 14 }
                            }
                            Label {
                                text: Math.floor(planner.focusedMinutes) + " min focused today"
                                color: Theme.success
                                font.pixelSize: 13
                            }
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: todayScroll.availableWidth >= 850 ? 2 : 1
                            columnSpacing: 18
                            rowSpacing: 18
                            AppPanel {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignTop
                                Layout.preferredWidth: 440
                                contentItem: ColumnLayout {
                                    spacing: 14
                                    Label { text: "IN YOUR DAY"; color: Theme.accent; font.pixelSize: 11; font.weight: Font.Bold }
                                    Label {
                                        Layout.fillWidth: true
                                        text: planner.nextTitle || "Room for your next priority."
                                        color: Theme.text
                                        font.pixelSize: 23
                                        font.weight: Font.DemiBold
                                        wrapMode: Text.Wrap
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: planner.nextTime || "Capture a task and give it a place in your day."
                                        color: Theme.muted
                                        wrapMode: Text.Wrap
                                    }
                                    AppButton { text: "Plan a task"; compact: true; onClicked: window.page = 1 }
                                }
                            }
                            CapturePanel {
                                id: captureFocus
                                Layout.fillWidth: true
                                Layout.preferredWidth: 360
                                Layout.alignment: Qt.AlignTop
                            }
                        }
                        AppPanel {
                            Layout.fillWidth: true
                            contentItem: ColumnLayout {
                                spacing: 14
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Today's agenda"; color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold; Layout.fillWidth: true }
                                    Label { text: planner.agenda.length + (planner.agenda.length === 1 ? " block" : " blocks"); color: Theme.muted; font.pixelSize: 12 }
                                }
                                Label {
                                    Layout.fillWidth: true
                                    visible: planner.agenda.length === 0
                                    text: "No time blocks today. Schedule an open task when you know where it fits."
                                    color: Theme.muted
                                    wrapMode: Text.Wrap
                                }
                                Repeater {
                                    model: planner.agenda
                                    delegate: RowLayout {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        spacing: 14
                                        Label { text: modelData.start + "\n" + modelData.end; color: Theme.muted; font.pixelSize: 12; Layout.preferredWidth: 54 }
                                        Rectangle { width: 3; Layout.fillHeight: true; Layout.minimumHeight: 40; color: Theme.accent; radius: 2 }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4
                                            Label { Layout.fillWidth: true; text: modelData.title; color: Theme.text; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
                                            Label { text: modelData.category; color: Theme.muted; font.pixelSize: 12 }
                                        }
                                        AppButton {
                                            text: "Focus"
                                            compact: true
                                            visible: modelData.task_id !== null && modelData.task_id !== undefined && modelData.task_id >= 0
                                            onClicked: window.startTask(modelData.task_id)
                                        }
                                    }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Label { text: "Ready to work"; color: Theme.text; font.pixelSize: 19; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            AppButton { text: "All tasks"; compact: true; tone: "quiet"; onClicked: window.page = 1 }
                        }
                        Label {
                            Layout.fillWidth: true
                            visible: window.openTasks.length === 0
                            text: "Your inbox is clear. Add something above when you are ready."
                            color: Theme.muted
                            wrapMode: Text.Wrap
                        }
                        Repeater {
                            model: window.openTasks.slice(0, 3)
                            delegate: TaskCard {
                                required property var modelData
                                Layout.fillWidth: true
                                task: modelData
                                onFocusRequested: function(id) { window.startTask(id) }
                                onScheduleRequested: function(task) { window.openSchedule(task) }
                                onEditRequested: function(task) { window.openEdit(task) }
                                onCompleteRequested: function(id) { planner.toggleTask(id) }
                            }
                        }
                        Item { height: 12 }
                    }
                }

                ColumnLayout {
                    spacing: 16
                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            Layout.fillWidth: true
                            Label { text: "Tasks"; color: Theme.text; font.pixelSize: 30; font.weight: Font.Bold }
                            Label { text: "Capture it, give it time, then get to work."; color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        }
                        ComboBox {
                            objectName: "taskFilter"
                            model: ["Open", "Done", "All"]
                            Accessible.name: "Filter tasks"
                            onActivated: window.taskFilter = currentText
                        }
                    }
                    CapturePanel { namePrefix: "taskCapture"; Layout.fillWidth: true }
                    Label {
                        visible: window.displayedTasks.length === 0
                        text: taskFilter === "Done" ? "Completed tasks will appear here." : "Nothing in this view yet."
                        color: Theme.muted
                    }
                    ListView {
                        id: taskList
                        objectName: "taskList"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 10
                        model: window.displayedTasks
                        boundsBehavior: Flickable.StopAtBounds
                        property real retainedPosition: 0
                        property bool restoringPosition: false
                        onContentYChanged: if (!restoringPosition) retainedPosition = contentY
                        onModelChanged: {
                            restoringPosition = true
                            Qt.callLater(function() {
                                taskList.forceLayout()
                                taskList.contentY = Math.max(taskList.originY, Math.min(taskList.retainedPosition, taskList.originY + Math.max(0, taskList.contentHeight - taskList.height)))
                                taskList.restoringPosition = false
                            })
                        }
                        ScrollBar.vertical: ScrollBar { }
                        PrecisionWheel { flickable: taskList }
                        delegate: TaskCard {
                            required property var modelData
                            width: taskList.width - 12
                            task: modelData
                            onFocusRequested: function(id) { window.startTask(id) }
                            onScheduleRequested: function(task) { window.openSchedule(task) }
                            onEditRequested: function(task) { window.openEdit(task) }
                            onCompleteRequested: function(id) { planner.toggleTask(id) }
                        }
                    }
                }

                ScrollView {
                    id: focusScroll
                    objectName: "focusScroll"
                    contentWidth: availableWidth
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    PrecisionWheel { flickable: focusScroll.contentItem }
                    ColumnLayout {
                        width: focusScroll.availableWidth
                        spacing: 20
                        Label { text: "Focus"; color: Theme.text; font.pixelSize: 30; font.weight: Font.Bold }
                        Label { text: "One task. A little uninterrupted time."; color: Theme.muted }
                        AppPanel {
                            Layout.fillWidth: true
                            contentItem: ColumnLayout {
                                spacing: 20
                                Label {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: planner.focusPhase === "PAUSED" ? "PAUSED" : planner.focusPhase === "SHORT_BREAK" || planner.focusPhase === "LONG_BREAK" ? "TAKE A BREAK" : planner.focusRunning ? "FOCUS SESSION" : "READY WHEN YOU ARE"
                                    color: Theme.accent
                                    font.pixelSize: 12
                                    font.weight: Font.Bold
                                }
                                Label {
                                    Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter
                                    text: planner.focusRunning ? planner.focusTitle : "Choose your next task"
                                    color: Theme.text
                                    font.pixelSize: 22
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.Wrap
                                }
                                Label {
                                    objectName: "focusTimer"
                                    Layout.alignment: Qt.AlignHCenter
                                    text: Math.floor(planner.remainingSeconds / 60).toString().padStart(2, "0") + ":" + (planner.remainingSeconds % 60).toString().padStart(2, "0")
                                    color: Theme.text
                                    font.family: "Consolas"
                                    font.pixelSize: window.width < 1000 ? 64 : 84
                                    Accessible.name: "Remaining time " + text
                                }
                                ComboBox {
                                    id: focusTaskPicker
                                    objectName: "focusTaskPicker"
                                    Layout.fillWidth: true
                                    Layout.maximumWidth: 520
                                    Layout.alignment: Qt.AlignHCenter
                                    visible: !planner.focusRunning
                                    model: window.openTasks
                                    textRole: "title"
                                    Accessible.name: "Task to focus on"
                                }
                                RowLayout {
                                    Layout.alignment: Qt.AlignHCenter
                                    spacing: 10
                                    AppButton {
                                        objectName: "focusStart"
                                        text: "Start focus"
                                        tone: "primary"
                                        visible: !planner.focusRunning
                                        enabled: window.openTasks.length > 0
                                        onClicked: window.startTask(window.openTasks[focusTaskPicker.currentIndex].id)
                                    }
                                    AppButton {
                                        objectName: "focusToggle"
                                        text: planner.focusPhase === "PAUSED" ? "Resume" : "Pause"
                                        tone: "primary"
                                        visible: planner.focusRunning
                                        onClicked: planner.pauseResumeFocus()
                                    }
                                    AppButton {
                                        objectName: "focusStop"
                                        text: "End session"
                                        visible: planner.focusRunning
                                        onClicked: planner.stopFocus()
                                    }
                                }
                                AppButton {
                                    objectName: "focusComplete"
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "Finish task"
                                    visible: planner.focusRunning && planner.activeTaskId >= 0
                                    onClicked: planner.toggleTask(planner.activeTaskId)
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: planner.focusRunning ? "Ending a session saves the time you worked. Finish the task when the work is done." : "Your estimate helps you plan. Focus sessions use your saved timer duration."
                                    color: Theme.muted
                                    horizontalAlignment: Text.AlignHCenter
                                    font.pixelSize: 12
                                    wrapMode: Text.Wrap
                                }
                            }
                        }
                        AppButton { text: "Choose from your tasks"; visible: window.openTasks.length === 0; onClicked: window.page = 1 }
                    }
                }

                ScrollView {
                    id: reviewScroll
                    objectName: "reviewScroll"
                    contentWidth: availableWidth
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    PrecisionWheel { flickable: reviewScroll.contentItem }
                    ColumnLayout {
                        width: reviewScroll.availableWidth
                        spacing: 20
                        Label { text: "Review"; color: Theme.text; font.pixelSize: 30; font.weight: Font.Bold }
                        Label { text: "A clear view of what you finished and the time you recorded."; color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        GridLayout {
                            columns: 3
                            Layout.fillWidth: true
                            columnSpacing: 12
                            Repeater {
                                model: [{label: "All tasks", value: planner.taskCount}, {label: "Completed tasks", value: planner.completedCount}, {label: "Focus today", value: Math.floor(planner.focusedMinutes) + " min"}]
                                delegate: AppPanel {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    contentItem: ColumnLayout {
                                        spacing: 10
                                        Label { text: modelData.value; color: Theme.text; font.pixelSize: 28; font.weight: Font.Bold }
                                        Label { Layout.fillWidth: true; text: modelData.label; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
                                    }
                                }
                            }
                        }
                        AppPanel {
                            Layout.fillWidth: true
                            contentItem: ColumnLayout {
                                spacing: 16
                                Label { text: "Recent focus sessions"; color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold }
                                Label { visible: planner.recentSessions.length === 0; text: "Recorded sessions will appear here after you focus."; color: Theme.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                Repeater {
                                    model: planner.recentSessions
                                    delegate: RowLayout {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 4
                                            Label { Layout.fillWidth: true; text: modelData.title; color: Theme.text; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
                                            Label { Layout.fillWidth: true; text: modelData.date + "  ·  " + modelData.category + (modelData.estimated ? "  ·  Cycle estimate" : "  ·  Recorded focus"); color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
                                        }
                                        Label { text: modelData.minutes > 0 && modelData.minutes < 1 ? "<1 min" : Math.round(modelData.minutes * 10) / 10 + " min"; color: Theme.success; font.weight: Font.DemiBold }
                                    }
                                }
                            }
                        }
                        AppPanel {
                            Layout.fillWidth: true
                            contentItem: ColumnLayout {
                                spacing: 12
                                Label { text: "Your data"; color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold }
                                Label { Layout.fillWidth: true; text: planner.databasePath; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.WrapAnywhere; Accessible.name: "Database location " + text }
                                AppButton { objectName: "backupButton"; text: "Export a backup"; onClicked: backupDialog.open() }
                            }
                        }
                    }
                }
            }
            Label {
                objectName: "statusLabel"
                Layout.fillWidth: true
                text: planner.statusMessage
                visible: text.length > 0
                color: Theme.muted
                font.pixelSize: 12
                maximumLineCount: 2
                wrapMode: Text.Wrap
                elide: Text.ElideRight
            }
        }
    }

    Dialog {
        id: scheduleDialog
        objectName: "scheduleDialog"
        property var task: null
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(500, window.width - 48)
        height: Math.min(implicitHeight, window.height - 48)
        modal: true
        closePolicy: Popup.CloseOnEscape
        title: "Schedule a task"
        padding: 22
        background: Rectangle { color: Theme.surface; radius: 16; border.color: Theme.border }
        contentItem: ScrollView {
            id: scheduleScroll
            clip: true
            contentWidth: availableWidth
            implicitHeight: scheduleForm.implicitHeight
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            PrecisionWheel { flickable: scheduleScroll.contentItem }
            ColumnLayout {
            id: scheduleForm
            width: scheduleScroll.availableWidth
            spacing: 14
            Label { Layout.fillWidth: true; text: scheduleDialog.task ? scheduleDialog.task.title : ""; color: Theme.text; font.weight: Font.DemiBold; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight }
            Label { text: "Date (YYYY-MM-DD)"; color: Theme.muted; font.pixelSize: 12 }
            AppField { id: scheduleDate; objectName: "scheduleDate"; Layout.fillWidth: true; Accessible.name: "Scheduled date"; placeholderText: "2026-10-17" }
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    Label { text: "Start (24-hour time)"; color: Theme.muted; font.pixelSize: 12 }
                    AppField { id: scheduleStart; objectName: "scheduleStart"; Layout.fillWidth: true; Accessible.name: "Start time"; placeholderText: "09:00" }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Label { text: "End"; color: Theme.muted; font.pixelSize: 12 }
                    AppField { id: scheduleEnd; objectName: "scheduleEnd"; Layout.fillWidth: true; Accessible.name: "End time"; placeholderText: "09:25" }
                }
            }
            Label { Layout.fillWidth: true; visible: planner.errorMessage.length > 0; text: planner.errorMessage; color: Theme.danger; wrapMode: Text.Wrap }
            Label {
                Layout.fillWidth: true
                visible: scheduleDialog.task && scheduleDialog.task.blocks.some(function(block) { return !block.owns_event })
                text: "Detach removes the task link. The original calendar event or recurring series stays in your planner."
                color: Theme.muted
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
            Repeater {
                model: scheduleDialog.task && scheduleDialog.task.blocks ? scheduleDialog.task.blocks : []
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Label { Layout.fillWidth: true; text: modelData.start.slice(0, 10) + "  " + modelData.start.slice(11, 16) + "–" + modelData.end.slice(11, 16); color: Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap }
                    AppButton {
                        text: modelData.owns_event ? "Remove" : "Detach"
                        compact: true
                        tone: "danger"
                        onClicked: {
                            if (planner.removeBlock(modelData.id)) {
                                scheduleDialog.task = planner.tasks.find(function(task) { return task.id === scheduleDialog.task.id })
                            }
                        }
                    }
                }
            }
            }
        }
        footer: RowLayout {
            spacing: 10
            Item { Layout.fillWidth: true }
            AppButton { objectName: "scheduleCancel"; text: "Cancel"; onClicked: { planner.clearError(); scheduleDialog.close() } }
            AppButton {
                objectName: "scheduleSave"
                text: "Add time block"
                tone: "primary"
                onClicked: {
                    if (planner.scheduleTask(scheduleDialog.task.id, scheduleDate.text, scheduleStart.text, scheduleEnd.text)) scheduleDialog.close()
                }
            }
        }
    }

    Dialog {
        id: editDialog
        objectName: "editDialog"
        property var task: null
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(540, window.width - 48)
        modal: true
        closePolicy: Popup.CloseOnEscape
        title: "Edit task"
        padding: 22
        background: Rectangle { color: Theme.surface; radius: 16; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 12
            Label { text: "Task title"; color: Theme.muted; font.pixelSize: 12 }
            AppField { id: editTitle; objectName: "editTitle"; Layout.fillWidth: true; Accessible.name: "Task title" }
            RowLayout {
                Layout.fillWidth: true
                ComboBox { id: editCategory; objectName: "editCategory"; Layout.fillWidth: true; model: planner.categories; Accessible.name: "Task category" }
                SpinBox { id: editEstimate; objectName: "editEstimate"; from: 1; to: 1440; stepSize: 5; editable: true; Accessible.name: "Task estimate in minutes" }
            }
            Label { text: "Notes"; color: Theme.muted; font.pixelSize: 12 }
            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: 110
                TextArea {
                    id: editNotes
                    objectName: "editNotes"
                    wrapMode: TextEdit.Wrap
                    color: Theme.text
                    selectByMouse: true
                    Accessible.name: "Task notes"
                    background: Rectangle { color: Theme.background; radius: 8; border.color: Theme.border }
                }
            }
            Label { Layout.fillWidth: true; visible: planner.errorMessage.length > 0; text: planner.errorMessage; color: Theme.danger; wrapMode: Text.Wrap }
            AppButton {
                objectName: "deleteTask"
                text: "Delete task"
                tone: "danger"
                onClicked: deleteConfirm.open()
            }
        }
        footer: RowLayout {
            spacing: 10
            Item { Layout.fillWidth: true }
            AppButton { text: "Cancel"; onClicked: { planner.clearError(); editDialog.close() } }
            AppButton {
                objectName: "editSave"
                text: "Save changes"
                tone: "primary"
                onClicked: {
                    if (planner.editTask(editDialog.task.id, editTitle.text, editCategory.currentText, editNotes.text, editEstimate.value)) editDialog.close()
                }
            }
        }
    }

    Dialog {
        id: deleteConfirm
        objectName: "deleteConfirm"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(440, window.width - 48)
        modal: true
        title: "Delete this task?"
        padding: 22
        background: Rectangle { color: Theme.surface; radius: 16; border.color: Theme.border }
        contentItem: Label { text: "Time blocks created for this task will also be removed. Imported calendar events and recorded focus history are kept."; color: Theme.text; wrapMode: Text.Wrap }
        footer: RowLayout {
            spacing: 10
            Item { Layout.fillWidth: true }
            AppButton { text: "Keep task"; onClicked: deleteConfirm.close() }
            AppButton {
                objectName: "confirmDeleteTask"
                text: "Delete task"
                tone: "danger"
                onClicked: {
                    if (planner.deleteTask(editDialog.task.id)) { deleteConfirm.close(); editDialog.close() }
                    else deleteConfirm.close()
                }
            }
        }
    }

    FileDialog {
        id: backupDialog
        title: "Export a Timography backup"
        fileMode: FileDialog.SaveFile
        nameFilters: ["SQLite backup (*.db)"]
        defaultSuffix: "db"
        onAccepted: planner.exportBackup(selectedFile.toString())
    }
}
