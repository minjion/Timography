"""Run the new Qt workflow against a persistent preview copy of your planner.

The existing main.py remains the complete legacy app. An explicit --database
uses the selected database; the default preview never writes to its source.
"""
import argparse
from contextlib import closing
from logging.handlers import RotatingFileHandler
import logging
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from config import BASE_DIR, DB_PATH
from core.backups import BackupManager
from core.database import TimographyDB
from core.instance_lock import InstanceLock

logger = logging.getLogger(__name__)


def prepare_database(source_path, preview_path):
    """Snapshot a source once, including committed WAL data, without upgrading it.

    The caller holds the preview's InstanceLock. Subsequent runs always reuse
    the preview, even if its source has since changed or been removed.
    """
    source, target = Path(source_path).resolve(), Path(preview_path).resolve()
    if source == target or (source.exists() and target.exists() and os.path.samefile(source, target)):
        raise ValueError("The preview database must be separate from the existing planner.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    if not source.is_file() or source.stat().st_size == 0:
        return target
    handle, temporary_name = tempfile.mkstemp(prefix=".preview-", suffix=".db", dir=target.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as original:
            with closing(sqlite3.connect(str(temporary))) as copy:
                BackupManager._copy(original, copy)
        BackupManager(TimographyDB(":memory:")).validate_backup(temporary)
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Timography's new task-to-focus desktop workflow")
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--database", type=Path, help="Use this database directly (backed up before migration).")
    location.add_argument("--preview-database", type=Path,
                          help="Where to keep the independent preview copy; never replaces an existing preview.")
    options = parser.parse_args(argv)
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuickControls2 import QQuickStyle
        from PySide6.QtWidgets import QApplication, QMessageBox
        from desktop_qt.controller import PlannerController
    except ImportError as exc:
        print(f"Qt could not load: {exc}\nRun start-next.bat to install the preview dependencies.", file=sys.stderr)
        return 1

    QQuickStyle.setStyle("Basic")
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Timography Next")
    app.setOrganizationName("Timography")
    preview_mode = options.database is None
    target = (options.database or options.preview_database or Path(BASE_DIR) / "data" / "preview" / "timography.db").resolve()
    lock = InstanceLock(target)
    db = controller = engine = handler = None
    previous_exception_handler = sys.excepthook
    exit_code = 0
    try:
        if not lock.acquire():
            QMessageBox.information(None, "Timography", "This planner is already open. Switch to its existing window.")
            return 0
        if preview_mode:
            prepare_database(DB_PATH, target)
        db = TimographyDB(str(target))
        logs = target.parent / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(logs / "timography-next.log", maxBytes=1_000_000,
                                     backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        BackupManager(db).create_automatic_backup()
        db.initialize()
        db.recover_interrupted_pomodoros()
        controller = PlannerController(db, preview_mode=preview_mode)

        def report_exception(kind, value, trace):
            logger.error("Qt UI action failed", exc_info=(kind, value, trace))
            controller._fail(value)

        sys.excepthook = report_exception
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("planner", controller)
        engine.load(QUrl.fromLocalFile(str(Path(BASE_DIR) / "desktop_qt" / "qml" / "Main.qml")))
        if not engine.rootObjects():
            raise RuntimeError("The new interface could not load. See the log beside your preview database.")
        app.aboutToQuit.connect(controller.close)
        exit_code = app.exec()
    except Exception as exc:
        logger.exception("Timography Next startup failed")
        QMessageBox.critical(None, "Timography Next", f"The preview could not open:\n{exc}\n\nDatabase: {target}")
        exit_code = 1
    finally:
        if controller is not None:
            if not controller.close():
                exit_code = 1
            if app is not None:
                try:
                    app.aboutToQuit.disconnect(controller.close)
                except RuntimeError:
                    pass
        # Destroy QML while its context object and database still exist.
        if engine is not None:
            for window in engine.rootObjects():
                window.close()
            import shiboken6
            shiboken6.delete(engine)
        if db is not None:
            db.close()
        lock.release()
        sys.excepthook = previous_exception_handler
        if handler is not None:
            logging.getLogger().removeHandler(handler)
            handler.close()
    return exit_code


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
