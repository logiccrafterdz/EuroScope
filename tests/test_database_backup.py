import asyncio
import os
import shutil
from pathlib import Path

import pytest
from euroscope.data.storage import Storage


@pytest.fixture
def temp_db(tmp_path):
    """Create a temp database file for testing backups."""
    db_file = tmp_path / "test_backup.db"
    yield db_file


@pytest.mark.asyncio
async def test_database_backup_creates_file(temp_db):
    storage = Storage(str(temp_db))

    # 1. Add some data to the real DB
    await storage.set_memory("test_key", "test_value")

    # 2. Trigger backup
    backup_path = await storage.backup_database()

    # 3. Verify backup file exists
    assert backup_path != "in_memory"
    assert backup_path != ""
    assert os.path.exists(backup_path)

    # 4. Verify contents were copied
    import sqlite3
    conn = sqlite3.connect(backup_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT value FROM memory WHERE key='test_key'").fetchone()
    conn.close()
    assert row is not None
    assert row["value"] == "test_value"


@pytest.mark.asyncio
async def test_database_backup_pruning(temp_db):
    storage = Storage(str(temp_db))
    backup_dir = temp_db.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create 10 dummy old backups
    for i in range(10):
        dummy_file = backup_dir / f"test_backup_2024-01-{i:02d}_00-00-00.db"
        dummy_file.write_text("dummy")

    # 2. Trigger backup (should prune so only 7 remain)
    backup_path = await storage.backup_database()

    # 3. Verify pruning
    all_backups = list(backup_dir.glob("test_backup_*.db"))

    # We expect 7 backups total (6 newest dummies + 1 real backup = 7, after pruning 4 oldest)
    assert len(all_backups) == 7
    assert Path(backup_path) in all_backups
