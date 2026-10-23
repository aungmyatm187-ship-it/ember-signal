"""B4 Data Sync core — runtime (event-driven / cron) replacement for the build-time clone.

WHY THIS EXISTS
---------------
Until 2026-10-23, ember-signal-web got its real data only at BUILD time: the
Render build command cloned ember-signal-backend and regenerated data.db +
ember-signal-evidence.json. That means data parity is bounded by deploys: new
evidence approved in the backend does not appear in the storefront until the
next build. This module moves the exact same transform to RUNTIME, invoked by:

  * a signed webhook  POST /api/sync/run   (see sync_service.py) — event-driven,
    triggered the moment the backend publishes new evidence (GitHub
    repository_dispatch -> Actions -> signed POST), or
  * the GitHub Actions cron (every 30 min) — parity floor, and
  * a human with the key:  python sync_core.py --source ... --target ...

DESIGN CONTRACTS
----------------
1. BYTE-EXACT DETERMINISM. The transform is the same one embedded in the live
   Render build command (deploy dep-dbdbuiss72, validated 2026-10-23): same
   status mapping, same ordering, same field truncation. Given the same source
   db, the produced evidence records are byte-identical.

2. CHANGE DETECTION. A content hash (sha256 over the canonical records +
   brand rows) is compared with the hash stored in sync-state.json. If nothing
   changed, NOTHING is rewritten — updatedAt in the evidence doc stays at the
   last real change (honest timestamps, no gratuitous churn).

3. ATOMIC SWAP. Outputs are written to sibling temp files, fsynced, then
   os.replace()d into place. A crash mid-sync can never leave a half-written
   data.db or evidence file; readers see either the old or the new file.

4. SINGLE WRITER. A lockfile (O_CREAT | O_EXCL) with stale-lock breaking
   (10 min) prevents two concurrent syncs from interleaving os.replace calls.

5. HONEST REPORT. Every run appends/updates sync-state.json with counts,
   hashes, duration and outcome — GET /api/sync/status serves it verbatim.

Status mapping (backend review_status -> public status):
  approved               -> verified
  source_review_required -> pending
  unreviewed             -> observed
  rejected               -> EXCLUDED (never published)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# --- configuration (env-overridable) ---------------------------------------

DEFAULT_SOURCE_REPO = "https://github.com/highfive251677-wq/ember-signal-backend.git"
DEFAULT_SOURCE_DB_NAME = "ember_signal.db"
STATE_FILE = "sync-state.json"
LOCK_FILE = ".sync.lock"
LOCK_STALE_SECONDS = 600  # break locks older than 10 min

STATUS_MAP = {
    "approved": "verified",
    "source_review_required": "pending",
    "unreviewed": "observed",
    "rejected": None,  # excluded from publication
}
GROUP = {"verified": 0, "pending": 1, "observed": 2}


class SyncBusyError(RuntimeError):
    """Another sync is already running."""


class SyncError(RuntimeError):
    """The sync itself failed (bad source db, unwritable target...)."""


# --- transform (byte-exact with the deployed build command) ------------------


def build_records(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT e.id, e.title, e.source_url, e.observed_at, e.review_status, "
        "e.excerpt, i.name, e.platform FROM evidence_items e "
        "LEFT JOIN institutions i ON i.id = e.institution_id "
        "ORDER BY e.observed_at ASC, e.id ASC"
    ).fetchall()

    records: list[dict] = []
    for rid, title, source_url, observed_at, review_status, excerpt, inst_name, platform in rows:
        mapped = STATUS_MAP.get(review_status)
        if mapped is None:
            continue  # rejected: never published
        title = (title or "").strip() or "Signal from " + (inst_name or "unknown institution")
        summary = (excerpt or "").strip() or (
            "Captured " + str(platform) + " signal for " + (inst_name or "institution") + "."
        )
        records.append(
            {
                "id": str(rid),
                "title": title[:180],
                "source": (source_url or "")[:240] or "ember-signal-backend",
                "observedAt": (observed_at or "")[:80],
                "status": mapped,
                "summary": summary[:1200],
                "reference": "ember-signal-backend:evidence:" + str(rid),
            }
        )
    records.sort(key=lambda r: (GROUP[r["status"]], r["observedAt"], int(r["id"])))
    return records


def build_top_institutions(conn: sqlite3.Connection, limit: int = 10) -> list[tuple[str, str | None, float]]:
    return conn.execute(
        "SELECT i.name, MAX(i.city) AS city, COUNT(e.id) AS signals "
        "FROM evidence_items e JOIN institutions i ON i.id = e.institution_id "
        "GROUP BY i.name ORDER BY signals DESC, i.name ASC LIMIT ?",
        (limit,),
    ).fetchall()


def content_hash(records: list[dict], top: list[tuple[str, str | None, float]]) -> str:
    """Hash of the published CONTENT only (not updatedAt) — stable across
    no-op re-syncs so change detection works."""
    canonical = json.dumps(
        {"records": records, "top": [[name, city, n] for name, city, n in top]},
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# --- atomic writers -----------------------------------------------------------


def _atomic_write_text(target: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=target.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_sqlite(target: Path, top: list[tuple[str, str | None, float]]) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix="data.db.", suffix=".tmp")
    os.close(fd)
    os.unlink(tmp)  # sqlite3.connect wants to create it itself
    try:
        out = sqlite3.connect(tmp)
        try:
            out.execute(
                "CREATE TABLE brands (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT, country TEXT, brand_value REAL)"
            )
            for i, (name, city, n) in enumerate(top, 1):
                out.execute(
                    "INSERT INTO brands (id, name, country, brand_value) VALUES (?,?,?,?)",
                    (i, name, city, float(n)),
                )
            out.commit()
        finally:
            out.close()
        # fsync the finished db file before the swap
        fh = os.open(tmp, os.O_RDONLY)
        try:
            os.fsync(fh)
        finally:
            os.close(fh)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# --- lockfile ------------------------------------------------------------------


class _Lock:
    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    def __enter__(self) -> "_Lock":
        # Break a stale lock left by a crashed run.
        try:
            age = time.time() - self.path.stat().st_mtime
            if age > LOCK_STALE_SECONDS:
                self.path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            self.acquired = True
        except FileExistsError as exc:
            raise SyncBusyError("a sync is already running") from exc
        return self

    def __exit__(self, *exc) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass


# --- the sync -------------------------------------------------------------------


def sync(source_db: str, target_dir: str) -> dict:
    """Run the deterministic transform and swap outputs into place.

    Returns the report dict (also persisted to sync-state.json).
    Raises SyncBusyError / SyncError.
    """
    started = time.monotonic()
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    state_path = target / STATE_FILE

    if not os.path.isfile(source_db):
        raise SyncError(f"source db not found: {source_db}")

    previous_hash = None
    if state_path.exists():
        try:
            previous_hash = json.loads(state_path.read_text(encoding="utf-8")).get("contentHash")
        except (json.JSONDecodeError, OSError):
            previous_hash = None

    conn = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)  # read-only: we never touch the source
    try:
        records = build_records(conn)
        top = build_top_institutions(conn)
    finally:
        conn.close()

    new_hash = content_hash(records, top)
    changed = new_hash != previous_hash

    report: dict = {}

    with _Lock(target / LOCK_FILE):
        if changed:
            doc = {
                "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "records": records,
            }
            evidence_text = json.dumps(doc, ensure_ascii=False, indent=2)
            _atomic_write_text(target / "ember-signal-evidence.json", evidence_text)
            _atomic_write_sqlite(target / "data.db", top)
        # else: no-op — files keep their honest old timestamps.

        report = {
            "ok": True,
            "changed": changed,
            "contentHash": new_hash,
            "institutions": len(top),
            "records": len(records),
            "verified": sum(1 for r in records if r["status"] == "verified"),
            "pending": sum(1 for r in records if r["status"] == "pending"),
            "observed": sum(1 for r in records if r["status"] == "observed"),
            "rejectedExcluded": None,  # filled by caller when it knows the raw count
            "syncedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "durationMs": int((time.monotonic() - started) * 1000),
            "sourceDb": str(source_db),
        }
        _atomic_write_text(state_path, json.dumps(report, ensure_ascii=False, indent=2))

    return report


# --- CLI ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B4 runtime data sync (ember-signal-backend -> ember-signal-web files)")
    parser.add_argument("--source", required=True, help="path to the cloned backend ember_signal.db")
    parser.add_argument("--target", default=".", help="directory holding data.db + ember-signal-evidence.json")
    args = parser.parse_args(argv)

    try:
        report = sync(args.source, args.target)
    except SyncBusyError:
        print("SYNC BUSY: another sync holds the lock")
        return 0o755 if False else 2
    except SyncError as exc:
        print(f"SYNC FAILED: {exc}")
        return 1

    print(
        "SYNC OK: {institutions} institutions, {records} evidence records "
        "(verified={verified} pending={pending} observed={observed}) changed={changed} in {durationMs} ms".format(**report)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
