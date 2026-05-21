"""Folder watcher: on every new .SC2Replay file, run the ingest pipeline."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .ingest import ingest_file

log = logging.getLogger(__name__)


class _ReplayHandler(FileSystemEventHandler):
    def _process(self, src_path: str) -> None:
        p = Path(src_path)
        if p.suffix != ".SC2Replay":
            return
        # SC2 writes the file in stages; let it settle.
        for _ in range(10):
            try:
                size = p.stat().st_size
                time.sleep(0.5)
                if p.stat().st_size == size and size > 0:
                    break
            except FileNotFoundError:
                return
        try:
            ingest_file(p)
        except Exception:
            log.exception("Ingest failed for %s", p)

    def on_created(self, event):
        if not event.is_directory:
            threading.Thread(target=self._process, args=(event.src_path,), daemon=True).start()

    def on_moved(self, event):
        if not event.is_directory:
            threading.Thread(target=self._process, args=(event.dest_path,), daemon=True).start()


class ReplayWatcher:
    def __init__(self, folder: Path):
        self.folder = folder
        self._observer = Observer()

    def start(self) -> None:
        if not self.folder.exists():
            log.warning("Replay folder %s does not exist — watcher idle", self.folder)
            return
        self._observer.schedule(_ReplayHandler(), str(self.folder), recursive=True)
        self._observer.start()
        log.info("Watching %s", self.folder)

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=2)
