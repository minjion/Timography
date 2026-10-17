import QtQuick
import QtQuick.Controls
import "."

TextField {
    id: control
    implicitHeight: 42
    leftPadding: 12
    rightPadding: 12
    color: Theme.text
    placeholderTextColor: Theme.muted
    selectionColor: Theme.accent
    selectedTextColor: Theme.accentText
    font.family: Theme.family
    font.pixelSize: 14
    selectByMouse: true
    background: Rectangle {
        radius: 8
        color: Theme.background
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? Theme.accent : Theme.border
    }
}
