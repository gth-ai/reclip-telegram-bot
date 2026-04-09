import os
import time
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cleanup


def test_deletes_old_files(tmp_path):
    old_file = tmp_path / "old.mp4"
    old_file.write_bytes(b"x" * 100)
    os.utime(old_file, (time.time() - 7200, time.time() - 7200))

    new_file = tmp_path / "new.mp4"
    new_file.write_bytes(b"x" * 100)

    cleanup.DOWNLOADS_PATH = tmp_path
    cleanup.CLEANUP_MAX_AGE_HOURS = 1
    cleanup.CLEANUP_MAX_DISK_MB = 99999

    cleanup._run_cleanup()

    assert not old_file.exists()
    assert new_file.exists()


def test_enforces_disk_limit(tmp_path):
    for i in range(5):
        f = tmp_path / f"file{i}.mp4"
        f.write_bytes(b"x" * 1024 * 1024)
        os.utime(f, (time.time() - i * 10, time.time() - i * 10))

    cleanup.DOWNLOADS_PATH = tmp_path
    cleanup.CLEANUP_MAX_AGE_HOURS = 999
    cleanup.CLEANUP_MAX_DISK_MB = 3

    cleanup._run_cleanup()
    cleanup._enforce_disk_limit()

    remaining = list(tmp_path.iterdir())
    total_mb = sum(f.stat().st_size for f in remaining) / (1024 * 1024)
    assert total_mb <= 3


def test_handles_permission_error(tmp_path):
    f = tmp_path / "locked.mp4"
    f.write_bytes(b"x" * 100)
    os.utime(f, (time.time() - 7200, time.time() - 7200))

    cleanup.DOWNLOADS_PATH = tmp_path
    cleanup.CLEANUP_MAX_AGE_HOURS = 1

    # Make directory non-writable so unlink fails
    os.chmod(tmp_path, 0o555)
    try:
        cleanup._run_cleanup()
        # Should not crash, just log and skip
        assert f.exists()
    finally:
        os.chmod(tmp_path, 0o755)


def test_skips_directories(tmp_path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    cleanup.DOWNLOADS_PATH = tmp_path
    cleanup.CLEANUP_MAX_AGE_HOURS = 0
    cleanup._run_cleanup()
    assert subdir.exists()


def test_empty_directory(tmp_path):
    cleanup.DOWNLOADS_PATH = tmp_path
    cleanup._run_cleanup()


def test_nonexistent_directory():
    cleanup.DOWNLOADS_PATH = Path("/nonexistent/path")
    cleanup._run_cleanup()
