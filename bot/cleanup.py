import asyncio
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DOWNLOADS_PATH = Path(os.environ.get("DOWNLOADS_PATH", "/downloads"))
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "300"))
CLEANUP_MAX_AGE_HOURS = float(os.environ.get("CLEANUP_MAX_AGE_HOURS", "1"))
CLEANUP_MAX_DISK_MB = int(os.environ.get("CLEANUP_MAX_DISK_MB", "5000"))


async def cleanup_loop():
    logger.info(
        "Cleanup task started: path=%s interval=%ds max_age=%sh max_disk=%dMB",
        DOWNLOADS_PATH, CLEANUP_INTERVAL_SECONDS, CLEANUP_MAX_AGE_HOURS, CLEANUP_MAX_DISK_MB,
    )
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            _run_cleanup()
        except Exception:
            logger.exception("Cleanup cycle failed")


def _run_cleanup():
    if not DOWNLOADS_PATH.exists():
        return

    now = time.time()
    max_age_sec = CLEANUP_MAX_AGE_HOURS * 3600

    for entry in DOWNLOADS_PATH.iterdir():
        if not entry.is_file():
            continue
        try:
            age = now - entry.stat().st_mtime
            if age > max_age_sec:
                entry.unlink()
                logger.info("Deleted (age): %s (%.0fs old)", entry.name, age)
        except PermissionError:
            logger.warning("Permission denied: %s", entry.name)
        except Exception:
            logger.exception("Error checking file: %s", entry.name)

    _enforce_disk_limit()


def _enforce_disk_limit():
    if not DOWNLOADS_PATH.exists():
        return

    files = []
    total_bytes = 0
    for entry in DOWNLOADS_PATH.iterdir():
        if not entry.is_file():
            continue
        try:
            st = entry.stat()
            files.append((entry, st.st_mtime, st.st_size))
            total_bytes += st.st_size
        except Exception:
            continue

    max_bytes = CLEANUP_MAX_DISK_MB * 1024 * 1024
    if total_bytes <= max_bytes:
        return

    files.sort(key=lambda x: x[1])  # oldest first
    for path, _, size in files:
        if total_bytes <= max_bytes:
            break
        try:
            path.unlink()
            total_bytes -= size
            logger.info("Deleted (disk limit): %s (freed %d bytes)", path.name, size)
        except PermissionError:
            logger.warning("Permission denied: %s", path.name)
        except Exception:
            logger.exception("Error deleting: %s", path.name)
