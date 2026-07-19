"""Verify an isolated wheel includes and can execute all SQL migrations."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main() -> None:
    wheels = sorted(Path("dist").glob("rag_app-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("expected exactly one rag_app wheel in dist/")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with zipfile.ZipFile(wheels[0]) as archive:
            archive.extractall(root)
        migrations = sorted((root / "rag_app/infrastructure/sqlite/migrations").glob("*.sql"))
        if [path.name for path in migrations] != ["001_runs.sql", "002_request_fingerprint.sql"]:
            raise SystemExit("wheel does not contain the complete ordered migration set")
        code = """
from pathlib import Path
from rag_app.infrastructure.sqlite.runs import SQLiteRunRepository
import rag_app
root = Path.cwd()
assert str(rag_app.__file__).startswith(str(root))
repo = SQLiteRunRepository(root / 'clean.sqlite3')
repo.migrate()
import sqlite3
with sqlite3.connect(repo.database_path) as connection:
    versions = [row[0] for row in connection.execute('SELECT version FROM schema_migrations')]
    columns = [row[1] for row in connection.execute('PRAGMA table_info(runs)')]
assert versions == [1, 2]
assert 'request_fingerprint' in columns
"""
        environment = {**os.environ, "PYTHONPATH": str(root)}
        subprocess.run([sys.executable, "-c", code], cwd=root, env=environment, check=True)


if __name__ == "__main__":
    main()
