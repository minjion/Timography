import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

AppPanel {
    id: panel
    property string namePrefix: "capture"
    signal created()
    function focusTitle() { titleField.forceActiveFocus() }
    function save() {
        if (planner.createTask(titleField.text, category.currentText, estimate.value)) {
            titleField.clear()
            titleField.forceActiveFocus()
            panel.created()
        }
    }
    contentItem: ColumnLayout {
        spacing: 12
        Label {
            text: "Capture a task"
            color: Theme.text
            font.pixelSize: 17
            font.weight: Font.DemiBold
        }
        AppField {
            id: titleField
            objectName: panel.namePrefix + "Title"
            Layout.fillWidth: true
            placeholderText: "What needs your attention?"
            Accessible.name: "New task title"
            onAccepted: panel.save()
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 5
                Label { text: "Category"; color: Theme.muted; font.pixelSize: 12 }
                ComboBox {
                    id: category
                    objectName: panel.namePrefix + "Category"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 110
                    implicitHeight: 40
                    model: planner.categories
                    Accessible.name: "New task category"
                    Component.onCompleted: {
                        var index = find("Study")
                        if (index >= 0) currentIndex = index
                    }
                }
            }
            ColumnLayout {
                spacing: 5
                Label { text: "Estimate (min)"; color: Theme.muted; font.pixelSize: 12 }
                SpinBox {
                    id: estimate
                    objectName: panel.namePrefix + "Estimate"
                    implicitWidth: 120
                    implicitHeight: 40
                    from: 1
                    to: 1440
                    value: 25
                    stepSize: 5
                    editable: true
                    Accessible.name: "New task estimate in minutes"
                }
            }
        }
        AppButton {
            objectName: panel.namePrefix + "Button"
            Layout.fillWidth: true
            text: "Add task"
            tone: "primary"
            onClicked: panel.save()
        }
    }
}
