import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

Rectangle {
    id: card
    required property var task
    signal focusRequested(int taskId)
    signal scheduleRequested(var selectedTask)
    signal editRequested(var selectedTask)
    signal completeRequested(int taskId)
    implicitHeight: body.implicitHeight + 32
    color: Theme.surface
    radius: 13
    border.color: Theme.border

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 16
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            CheckBox {
                id: completion
                objectName: "taskComplete_" + card.task.id
                checked: Boolean(card.task.is_completed)
                padding: 0
                Accessible.name: (checked ? "Reopen " : "Complete ") + card.task.title
                onClicked: {
                    card.completeRequested(card.task.id)
                    // Restore the backend binding even if persistence was rejected.
                    completion.checked = Qt.binding(function() { return Boolean(card.task.is_completed) })
                }
                indicator: Rectangle {
                    implicitWidth: 23
                    implicitHeight: 23
                    radius: 7
                    color: completion.checked ? Theme.accent : Theme.background
                    border.width: completion.visualFocus ? 2 : 1
                    border.color: completion.checked || completion.visualFocus ? Theme.accent : Theme.border
                    Text {
                        anchors.centerIn: parent
                        text: completion.checked ? "✓" : ""
                        font.family: Theme.family
                        font.pixelSize: 17
                        color: Theme.accentText
                    }
                }
            }
            Label {
                Layout.fillWidth: true
                text: card.task.title
                color: card.task.is_completed ? Theme.muted : Theme.text
                font.family: Theme.family
                font.pixelSize: 15
                font.weight: Font.DemiBold
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
                Accessible.name: card.task.title
            }
            AppButton {
                objectName: "taskEdit_" + card.task.id
                text: "Edit"
                tone: "quiet"
                compact: true
                onClicked: card.editRequested(card.task)
            }
        }
        Label {
            Layout.fillWidth: true
            Layout.leftMargin: 33
            text: card.task.category + "  ·  " + card.task.estimate_minutes + " min estimate" + (card.task.focus_seconds > 0 ? "  ·  " + Math.floor(card.task.focus_seconds / 60) + " min recorded" : "")
            color: Theme.muted
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        Label {
            Layout.fillWidth: true
            Layout.leftMargin: 33
            visible: card.task.blocks && card.task.blocks.length > 0
            text: {
                if (!card.task.blocks || card.task.blocks.length === 0) return ""
                var block = card.task.blocks[0]
                return block.start.slice(0, 10) + "  ·  " + block.start.slice(11, 16) + "–" + block.end.slice(11, 16) + (card.task.blocks.length > 1 ? "  +" + (card.task.blocks.length - 1) + " more" : "")
            }
            color: Theme.accent
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 33
            spacing: 8
            visible: !card.task.is_completed
            AppButton {
                objectName: "taskFocus_" + card.task.id
                text: "Focus"
                tone: "primary"
                compact: true
                onClicked: card.focusRequested(card.task.id)
            }
            AppButton {
                objectName: "taskSchedule_" + card.task.id
                text: "Schedule"
                compact: true
                onClicked: card.scheduleRequested(card.task)
            }
            Item { Layout.fillWidth: true }
        }
    }
}
