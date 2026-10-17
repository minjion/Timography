import QtQuick
import QtQuick.Controls
import "."

Button {
    id: control
    property string tone: "secondary"
    property bool compact: false
    property string hint: ""
    implicitHeight: compact ? 34 : 42
    implicitWidth: Math.max(compact ? 68 : 100, contentItem.implicitWidth + leftPadding + rightPadding)
    leftPadding: compact ? 12 : 18
    rightPadding: leftPadding
    topPadding: 8
    bottomPadding: 8
    font.family: Theme.family
    font.pixelSize: compact ? 13 : 14
    font.weight: Font.DemiBold
    hoverEnabled: true
    Accessible.name: text
    ToolTip.visible: hovered && hint.length > 0
    ToolTip.text: hint
    background: Rectangle {
        radius: 9
        color: control.tone === "primary" ? Theme.accent : control.tone === "danger" ? Theme.dangerSoft : control.tone === "quiet" ? "transparent" : Theme.raised
        opacity: !control.enabled ? 0.45 : control.down ? 0.7 : control.hovered ? 0.86 : 1
        border.width: control.visualFocus ? 2 : control.tone === "secondary" ? 1 : 0
        border.color: control.visualFocus ? Theme.accent : Theme.border
    }
    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? Theme.muted : control.tone === "primary" ? Theme.accentText : control.tone === "danger" ? Theme.danger : Theme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
