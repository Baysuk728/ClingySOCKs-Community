"""
Database Backup Script — Dumps all tables to a timestamped folder.

Each table is exported as:
  - .csv (data)
  - .sql (CREATE TABLE DDL + INSERT statements)

Usage:
  python scripts/backup_db.py
"""

import csv
import os
import sys
from datetime import datetime

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text, MetaData
from src.db.session import engine


def backup_database():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups", timestamp)
    os.makedirs(backup_dir, exist_ok=True)

    inspector = inspect(engine)
    table_names = sorted(inspector.get_table_names())

    print(f"📦 Backing up {len(table_names)} tables to: {backup_dir}")
    print(f"   Tables: {', '.join(table_names)}\n")

    total_rows = 0

    with engine.connect() as conn:
        for table_name in table_names:
            try:
                # Get row count
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()

                # Fetch all rows
                result = conn.execute(text(f'SELECT * FROM "{table_name}"'))
                columns = list(result.keys())
                rows = result.fetchall()

                # ── CSV export ──
                csv_path = os.path.join(backup_dir, f"{table_name}.csv")
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(columns)
                    for row in rows:
                        writer.writerow([_serialize(v) for v in row])

                # ── SQL export (INSERT statements) ──
                sql_path = os.path.join(backup_dir, f"{table_name}.sql")
                with open(sql_path, "w", encoding="utf-8") as f:
                    # DDL
                    ddl = _get_create_table_ddl(conn, table_name)
                    if ddl:
                        f.write(f"-- DDL for {table_name}\n")
                        f.write(ddl + ";\n\n")

                    # INSERT statements
                    f.write(f"-- Data for {table_name} ({count} rows)\n")
                    for row in rows:
                        values = ", ".join(_sql_escape(v) for v in row)
                        cols = ", ".join(f'"{c}"' for c in columns)
                        f.write(f'INSERT INTO "{table_name}" ({cols}) VALUES ({values});\n')

                total_rows += count
                status = f"✅ {table_name}: {count} rows"
                print(status)

            except Exception as e:
                print(f"❌ {table_name}: {e}")

    # Summary
    print(f"\n{'='*50}")
    print(f"✅ Backup complete: {len(table_names)} tables, {total_rows} total rows")
    print(f"📁 Location: {backup_dir}")
    print(f"{'='*50}")

    return backup_dir


def _get_create_table_ddl(conn, table_name: str) -> str:
    """Get CREATE TABLE DDL from PostgreSQL catalog."""
    try:
        # pg_dump-style: use information_schema
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable, column_default,
                   character_maximum_length
            FROM information_schema.columns
            WHERE table_name = :table
            ORDER BY ordinal_position
        """), {"table": table_name})
        columns = result.fetchall()

        if not columns:
            return ""

        col_defs = []
        for col in columns:
            name, dtype, nullable, default, max_len = col
            parts = [f'    "{name}"']
            if max_len:
                parts.append(f"{dtype}({max_len})")
            else:
                parts.append(dtype)
            if nullable == "NO":
                parts.append("NOT NULL")
            if default:
                parts.append(f"DEFAULT {default}")
            col_defs.append(" ".join(parts))

        return f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n' + ",\n".join(col_defs) + "\n)"
    except Exception:
        return ""


def _serialize(value):
    """Serialize a value for CSV."""
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _sql_escape(value):
    """Escape a value for SQL INSERT."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        import json
        s = json.dumps(value, ensure_ascii=False, default=str)
        return "'" + s.replace("'", "''") + "'"
    s = str(value)
    return "'" + s.replace("'", "''") + "'"


if __name__ == "__main__":
    backup_database()
