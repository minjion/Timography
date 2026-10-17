pragma Singleton
import QtQuick

QtObject {
    readonly property bool dark: planner.darkMode
    readonly property color background: dark ? "#15171d" : "#f5f6fa"
    readonly property color surface: dark ? "#1d2028" : "#ffffff"
    readonly property color raised: dark ? "#272b36" : "#eef0f7"
    readonly property color border: dark ? "#343946" : "#e1e5ee"
    readonly property color text: dark ? "#f2f3f8" : "#202637"
    readonly property color muted: dark ? "#a7afc0" : "#646e83"
    readonly property color accent: dark ? "#99a6ff" : "#4d62df"
    readonly property color accentSoft: dark ? "#303752" : "#edf0ff"
    readonly property color accentText: dark ? "#161b34" : "#ffffff"
    readonly property color success: dark ? "#73c5a7" : "#267b60"
    readonly property color successSoft: dark ? "#203b34" : "#eaf5ef"
    readonly property color danger: dark ? "#ffaaa9" : "#b9323b"
    readonly property color dangerSoft: dark ? "#47272e" : "#fff0f1"
    readonly property string family: "Segoe UI"
}
