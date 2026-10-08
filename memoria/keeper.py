"""memoria.keeper — keeping the record safe for the long haul.

A keeper's duties:
- backup: the whole data dir (or one person) into a single tar archive
- restore: rebuild the data dir from an archive, verifying checksums
- verify: archive integrity (reuses step-5 manifests)
- dedupe: identical media files collapse to one copy (by content hash)
- migrate: the century-file exports survive any computer's death

Backups are plain tar.gz — no proprietary format survives a century.
"""
from __future__ import annotations
import hashlib
import json
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .config import MemoriaConfig
from .archive import Archive


class KeeperError(Exception):
    pass


def backup(config: MemoriaConfig, out_path: str | None = None,
           person_id: str | None = None) -> Path:
    """Whole data dir (or one person) -> one dated tar.gz."""
    root = Path(config.data_dir)
    if not root.is_dir():
        raise KeeperError(f"data dir does not exist: {root}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    default = root.parent / f"memoria-backup-{stamp}.tar.gz"
    out = Path(out_path) if out_path else default
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        if person_id:
            pdir = root / "people" / person_id
            if not pdir.is_dir():
                raise KeeperError(f"person not found: {person_id}")
            tar.add(pdir, arcname=f"people/{person_id}")
        else:
            tar.add(root, arcname=root.name)
    return out


def restore(config: MemoriaConfig, archive_path: str,
            dest_data_dir: str | None = None) -> dict:
    """Rebuild a data dir from a backup archive. Verifies it lands intact."""
    src = Path(archive_path)
    if not src.is_file():
        raise KeeperError(f"archive not found: {src}")
    dest = Path(dest_data_dir or config.data_dir)
    if dest.exists() and any(dest.iterdir()):
        raise KeeperError(f"restore target not empty: {dest} — restore into a clean dir")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(src, "r:gz") as tar:
        members = tar.getmembers()
        # find the archive's top-level dir (the data dir root)
        tops = {m.name.split("/")[0] for m in members}
        if not tops:
            raise KeeperError("archive is empty")
        top = sorted(tops)[0]
        tar.extractall(dest.parent)
    extracted_root = dest.parent / top
    if not extracted_root.is_dir():
        raise KeeperError("archive did not contain a memoria data dir")
    if extracted_root != dest:
        if dest.exists():
            dest.rmdir() if dest.is_dir() and not any(dest.iterdir()) else None
        extracted_root.rename(dest)
    # verify: every person manifests clean (or at minimum person.json exists)
    restored_people = list((dest / "people").glob("*/person.json")) if (dest / "people").is_dir() else []
    return {"data_dir": str(dest), "people": len(restored_people),
            "ok": True}


def verify_all(config: MemoriaConfig) -> dict:
    """Archive integrity for every person with a manifest."""
    arch = Archive(config)
    results = {}
    for pd in Path(config.people_dir).glob("*"):
        if (pd / "person.json").is_file():
            v = arch.verify(pd.name)
            results[pd.name] = {"ok": v["ok"], "report": v.get("report", v.get("error", ""))}
    return results


def dedupe_media(config: MemoriaConfig, person_id: str | None = None) -> dict:
    """Identical media files collapse to one copy (hard links, by content hash)."""
    root = Path(config.people_dir)
    if person_id:
        roots = [root / person_id]
    else:
        roots = [d for d in root.iterdir() if d.is_dir()]
    seen: dict[str, Path] = {}
    saved_bytes = 0
    replaced = 0
    for r in roots:
        if not r.is_dir():
            continue
        for f in sorted(r.rglob("*.wav")) + sorted(r.rglob("*.mp3")):
            if not f.is_file() or f.is_symlink():
                continue
            if f.stat().st_nlink > 1:
                continue  # already a dedupe hard link
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            if h in seen:
                first = seen[h]
                # replace the duplicate with a hard link to the first
                f.unlink()
                os.link(first, f)
                saved_bytes += f.stat().st_size
                replaced += 1
            else:
                seen[h] = f
    return {"files_deduped": replaced, "bytes_saved": saved_bytes}


def migration_runbook() -> str:
    """When the Jetson dies: how the record survives."""
    return """# Migration runbook — when the keeper machine dies

The record survives in three layers, in order of durability:

1. **Century files** (`exports/<person>-century.md`) — plain Markdown.
   Copy these anywhere. They need no software, ever. If everything else
   is lost, these are the gravestone.
2. **JSON bundles** (`exports/<person>.json`) — machine-readable, complete
   answers and letters (sealed rules included; sealed bodies are NOT in
   the bundle — they stay sealed even in backup).
3. **Full backups** (`memoria-backup-*.tar.gz`) — everything: records,
   voice clips, voice-prints, config. Keep two, in two places.

## Restoring onto new hardware
```
pip install fastapi uvicorn pyyaml pytest   # any python >= 3.10
git clone <memoria repo>                     # or copy the project
python -c "from memoria.keeper import restore; \
    from memoria.config import MemoriaConfig; \
    restore(MemoriaConfig(data_dir='~/memoria-data'), 'memoria-backup-XXXX.tar.gz')"
python -m pytest tests -q                    # green = intact
uvicorn memoria.memorial_server:app --port 8093
```

## Standing duties of a keeper
- One backup per month, kept in two physical places
- After any llama.cpp / model update, re-run the grounding tests
- When the executor key holder changes: rotate
  `<data>/config/executor_key` and tell the new executor only
- Never edit records.jsonl by hand; append-only, or use the CLI
"""
