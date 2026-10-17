import QtQuick

// Preserve pixel-only precision events even when a driver reports a mouse source.
// Ordinary angle-based wheel events continue through Qt's native Flickable path.
WheelHandler {
    required property var flickable
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    onWheel: function(event) {
        if (!flickable || !event.pixelDelta.y) {
            event.accepted = false
            return
        }
        var lower = flickable.originY || 0
        var upper = lower + Math.max(0, flickable.contentHeight - flickable.height)
        flickable.contentY = Math.max(lower, Math.min(upper, flickable.contentY - event.pixelDelta.y))
        event.accepted = true
    }
}
