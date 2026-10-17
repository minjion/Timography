"""Versioned, additive task storage shared by the desktop frontends.

checklist_items.id remains the canonical task identity. Existing source events,
completion timestamps and measured focus rows are never rewritten by migration.
"""
from datetime import date, datetime


TASK_SCHEMA_VERSION = 1


def migrate_tasks(connection):
    """Call after the legacy tables exist, while holding the database lock."""
    if connection.in_transaction:
        raise RuntimeError("Finish the current transaction before migrating tasks.")
    row = connection.execute("SELECT value FROM settings WHERE key = 'task_schema_version'").fetchone()
    version = int(row[0]) if row else 0
    if version > TASK_SCHEMA_VERSION:
        raise ValueError("This database needs a newer version of Timography.")
    if version == TASK_SCHEMA_VERSION:
        return
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""CREATE TABLE task_details (
            task_id INTEGER PRIMARY KEY,
            category TEXT,
            notes TEXT,
            estimate_minutes INTEGER CHECK(estimate_minutes > 0)
        )""")
        connection.execute("""CREATE TABLE task_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            start TEXT NOT NULL,
            end TEXT NOT NULL,
            event_id INTEGER,
            source_routine_id INTEGER,
            owns_event INTEGER NOT NULL DEFAULT 0 CHECK(owns_event IN (0, 1)),
            CHECK(end > start)
        )""")
        connection.execute("CREATE INDEX task_blocks_task ON task_blocks(task_id, start)")
        connection.execute("CREATE INDEX task_blocks_event ON task_blocks(event_id)")
        connection.execute("""CREATE TABLE task_session_links (
            session_id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL
        )""")
        connection.execute("CREATE INDEX task_sessions_task ON task_session_links(task_id)")
        rows = connection.execute("""SELECT c.id, c.date, c.event_id, c.routine_id,
            COALESCE(e.start_time, r.start_time) AS start_time,
            COALESCE(e.end_time, r.end_time) AS end_time
            FROM checklist_items c LEFT JOIN events e ON e.id = c.event_id
            LEFT JOIN routines r ON r.id = c.routine_id
            WHERE e.id IS NOT NULL OR r.id IS NOT NULL""").fetchall()
        for task in rows:
            try:
                day = date.fromisoformat(task["date"])
                start = datetime.fromisoformat(f"{day.isoformat()}T{task['start_time']}:00")
                end = datetime.fromisoformat(f"{day.isoformat()}T{task['end_time']}:00")
                if start >= end:
                    continue
            except (TypeError, ValueError):
                # Malformed old rows remain available as tasks; migration never discards them.
                continue
            connection.execute("INSERT INTO task_blocks (task_id, start, end, event_id, source_routine_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (task["id"], start.isoformat(), end.isoformat(), task["event_id"], task["routine_id"]))
        connection.execute("""INSERT INTO task_session_links (session_id, task_id)
            SELECT p.id, MIN(c.id) FROM pomodoro_sessions p JOIN checklist_items c
            ON c.event_id = p.event_id AND c.date = p.date
            WHERE p.event_id IS NOT NULL GROUP BY p.id HAVING COUNT(c.id) = 1""")

        # Projections are maintained for block changes after migration. Backfill above
        # intentionally runs first so every legacy checklist row stays byte-for-byte intact.
        projection = """UPDATE checklist_items SET
            date = COALESCE((SELECT substr(start, 1, 10) FROM task_blocks
                WHERE task_id = {task} ORDER BY start, id LIMIT 1),
                CASE WHEN is_completed = 1 AND NOT EXISTS
                    (SELECT 1 FROM task_details WHERE task_id = {task}) THEN date ELSE '' END),
            event_id = (SELECT event_id FROM task_blocks
                WHERE task_id = {task} ORDER BY start, id LIMIT 1),
            routine_id = (SELECT source_routine_id FROM task_blocks
                WHERE task_id = {task} ORDER BY start, id LIMIT 1)
            WHERE id = {task};"""
        for operation, reference in (("INSERT", "NEW"), ("DELETE", "OLD"), ("UPDATE", "NEW")):
            connection.execute(f"CREATE TRIGGER task_block_{operation.lower()}_projection "
                f"AFTER {operation} ON task_blocks BEGIN "
                + projection.format(task=f"{reference}.task_id") + " END")
        connection.execute("""CREATE TRIGGER task_event_deleted AFTER DELETE ON events BEGIN
            DELETE FROM task_blocks WHERE event_id = OLD.id;
        END""")
        connection.execute("""CREATE TRIGGER task_event_retimed
            AFTER UPDATE OF date, start_time, end_time ON events BEGIN
            UPDATE task_blocks SET
                start = CASE WHEN owns_event = 1 OR NEW.recurring = 'none'
                    THEN NEW.date ELSE substr(start, 1, 10) END || 'T' || NEW.start_time || ':00',
                end = CASE WHEN owns_event = 1 OR NEW.recurring = 'none'
                    THEN NEW.date ELSE substr(end, 1, 10) END || 'T' || NEW.end_time || ':00'
                WHERE event_id = NEW.id;
        END""")
        # Tasks created through the legacy UI after migration join the same model.
        # Existing blocks are retained when legacy Undo restores a checklist ID.
        connection.execute("""CREATE TRIGGER task_legacy_inserted
            AFTER INSERT ON checklist_items
            WHEN NEW.date != '' AND NOT EXISTS (SELECT 1 FROM task_blocks WHERE task_id = NEW.id)
            BEGIN
            INSERT INTO task_blocks (task_id, start, end, event_id, source_routine_id)
                SELECT NEW.id, NEW.date || 'T' || e.start_time || ':00',
                    NEW.date || 'T' || e.end_time || ':00', e.id, NULL
                FROM events e WHERE e.id = NEW.event_id AND e.end_time > e.start_time
                    AND time(e.start_time) IS NOT NULL AND time(e.end_time) IS NOT NULL;
            INSERT INTO task_blocks (task_id, start, end, event_id, source_routine_id)
                SELECT NEW.id, NEW.date || 'T' || r.start_time || ':00',
                    NEW.date || 'T' || r.end_time || ':00', NULL, r.id
                FROM routines r WHERE r.id = NEW.routine_id AND NEW.event_id IS NULL
                    AND r.end_time > r.start_time
                    AND time(r.start_time) IS NOT NULL AND time(r.end_time) IS NOT NULL;
        END""")
        connection.execute("INSERT INTO settings (key, value) VALUES ('task_schema_version', ?)",
                           (str(TASK_SCHEMA_VERSION),))
