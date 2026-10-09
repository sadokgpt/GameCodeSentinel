"""Filesystem and scan safeguards for GameCode Sentinel.

Only local SQLite snapshots are created; no personal data is uploaded.
"""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager, closing
from datetime import datetime
from pathlib import Path

from filelock import FileLock, Timeout


@contextmanager
def operation_lock(data_dir: Path, purpose: str, timeout: float = 0):
    """A process-safe lock, shared by EXE, GUI and scheduled CLI jobs."""
    data_dir.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(data_dir / f"{purpose}.lock"))
    try:
        lock.acquire(timeout=timeout)
    except Timeout:
        yield False
        return
    try:
        yield True
    finally:
        lock.release()


def backup_sqlite(db_path: Path, keep: int = 7, min_interval_hours: int = 24,
                  force: bool = False) -> Path | None:
    """Consistent SQLite online backup, including WAL; rotate only our own snapshots."""
    db_path = Path(db_path)
    if not db_path.is_file():
        return None
    target_dir = db_path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    backups = sorted(target_dir.glob("codes-*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not force and backups and time.time() - backups[0].stat().st_mtime < min_interval_hours * 3600:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = target_dir / f"codes-{stamp}.sqlite3"
    staging = target_dir / f".codes-{stamp}.tmp"
    try:
        with closing(sqlite3.connect(str(db_path), timeout=30)) as source:
            with closing(sqlite3.connect(str(staging), timeout=30)) as dest:
                source.backup(dest)
                result = dest.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise sqlite3.DatabaseError(f"Backup non integro: {result}")
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)
    for old in backups[max(0, keep - 1):]:
        old.unlink(missing_ok=True)
    return destination


def restore_sqlite(db_path: Path, backup_path: Path) -> Path:
    """Restore a verified snapshot after taking an additional safety copy.

    Caller must hold the scan lock, otherwise another process could write during restore.
    """
    db_path = Path(db_path)
    backup_path = Path(backup_path).resolve()
    expected_dir = (db_path.parent / "backups").resolve()
    if backup_path.parent != expected_dir or not backup_path.name.startswith("codes-"):
        raise ValueError("È possibile ripristinare solo un backup creato da GameCodeSentinel")
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    with closing(sqlite3.connect(str(backup_path))) as source:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("Backup danneggiato")
        # Force a separate snapshot so undo is possible even after restoration.
        backup_sqlite(db_path, force=True)
        with closing(sqlite3.connect(str(db_path), timeout=30)) as target:
            source.backup(target)
    return backup_path


def plausible_tracker_page(html: str, game: str) -> bool:
    """Only count a *zero-candidate* secondary tracker as readable when recognizable.

    A site navigation page, cookie wall or soft-404 must not count as evidence
    that previously listed promo codes have disappeared.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    text = soup.get_text(" ", strip=True).casefold()
    title = (soup.title.get_text(" ", strip=True) if soup.title else "").casefold()
    needles = {
        "AION 2": ("aion 2", "aion2"),
        "Genshin Impact": ("genshin",),
        "Aniimo": ("aniimo",),
    }
    game_mentioned = any(word in text or word in title for word in needles.get(game, (game.casefold(),)))
    code_mentioned = any(word in text for word in ("code", "coupon", "redeem", "codic", "gift code"))
    return len(text) >= 180 and game_mentioned and code_mentioned
