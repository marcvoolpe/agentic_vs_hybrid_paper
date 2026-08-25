"""Export telemetry ExtraModel tables to analysis-ready CSV files."""

from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / 'analysis' / 'data'

# Several apps define a table per suffix (intro_player, experiment_player).
# Without this prefix the suffix match returns whichever was created first.
APP_NAME = 'experiment'


def _database_path() -> Path:
    url = os.environ.get('DATABASE_URL', '')
    if url.startswith('sqlite:///'):
        return Path(url.replace('sqlite:///', ''))
    return ROOT / 'db.sqlite3'


def _find_table(conn: sqlite3.Connection, suffix: str) -> str | None:
    tables = [
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    ]
    preferred = f'{APP_NAME}{suffix}'
    if preferred in tables:
        return preferred
    for name in tables:
        if name.endswith(suffix):
            return name
    return None


def _write_rows(cursor, path: Path) -> int:
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    return len(rows)


def _export_table(conn: sqlite3.Connection, table: str, path: Path) -> int:
    return _write_rows(conn.execute(f'SELECT * FROM {table}'), path)


def export_tables(output_dir: Path | None = None) -> dict[str, tuple[Path, int]]:
    """Dump every row of every session currently in the database.

    The queries are unfiltered, so a single run after the last room captures
    all rooms and rounds accumulated in the database so far.
    """
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = _database_path()
    conn = sqlite3.connect(db_path)
    outputs = {}
    mapping = {
        'offer_events.csv': '_offerevent',
        'draft_offers.csv': '_draftoffer',
        'llm_calls.csv': '_llmcall',
    }
    try:
        for filename, suffix in mapping.items():
            table = _find_table(conn, suffix)
            if table:
                path = output_dir / filename
                count = _export_table(conn, table, path)
                outputs[filename] = (path, count)

        player_table = _find_table(conn, '_player')
        group_table = _find_table(conn, '_group')
        if player_table and group_table:
            path = output_dir / 'rounds.csv'
            query = f'''
                SELECT p.*, g.*
                FROM {player_table} AS p
                LEFT JOIN {group_table} AS g ON p.group_id = g.id
            '''
            count = _write_rows(conn.execute(query), path)
            outputs['rounds.csv'] = (path, count)
    finally:
        conn.close()

    return outputs


if __name__ == '__main__':
    results = export_tables()
    for name, (path, count) in results.items():
        print(f'Wrote {name} -> {path} ({count} rows)')
    if any(count == 0 for _, count in results.values()):
        print('\nWARNING: at least one table exported 0 rows.')
        print('The database may have been reset since the sessions ran.')
