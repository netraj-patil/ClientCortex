"""Background poller: notices changes made outside this API and invalidates dependent cache entries.

Only tables that currently have cached answers are checked, so the cost stays small.
"""
import logging
import threading

from . import db
from .cache_service import CacheService

log = logging.getLogger("crm.watcher")


class TableWatcher:
    def __init__(self, cache: CacheService, interval_seconds: int):
        self.cache = cache
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="table-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.scan_once()
            except Exception:
                log.exception("watcher scan failed")

    def scan_once(self) -> None:
        for conn_id, table in self.cache.tracked_tables():
            try:
                _, ro_engine = db.engines(conn_id)
                current = db.table_fingerprint(ro_engine, table)
            except db.ConnectionNotFound:
                continue
            except Exception:
                log.exception("could not check %s.%s", conn_id, table)
                continue

            baseline = self.cache.get_fingerprint(conn_id, table)
            if baseline is None:
                self.cache.set_fingerprint(conn_id, table, current)
            elif baseline != current:
                removed = self.cache.invalidate_table(conn_id, table)
                log.info("change detected in %s.%s, removed %d cache entries", conn_id, table, removed)
