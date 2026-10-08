"""memoria.archive — the durable record of a life.

The archive holds everything about one person: answers, letters, voice samples,
sessions. It maintains a checksummed manifest (tamper-evident) and exports:

- a JSON bundle (machine-readable, complete)
- a "century file" — Markdown, human-readable, self-describing, no proprietary
  formats. If every computer dies, the century file is the gravestone.
"""
from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .config import MemoriaConfig
from .interview import InterviewStore
from .storage import sha256_file, atomic_write, atomic_write_json

MANIFEST_VERSION = 1
CHAPTER_TITLES = {"roots": "Roots", "growing": "Growing", "love": "Love",
                  "work": "Work", "wisdom": "Wisdom", "regrets": "Regrets",
                  "joy": "Joy", "farewells": "Farewells", "custom": "Personal Questions"}


class ArchiveError(Exception):
    pass


def _chapter_of(question_id: str) -> str:
    """Question ids look like q_starter_roots_3 — chapter is the third field."""
    parts = question_id.split("_")
    if len(parts) >= 4 and parts[0] == "q":
        return parts[2]
    return "custom"


def _file_entry(path: Path, rel: str) -> dict:
    return {"path": rel, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


class Archive:
    """One person's archive: manifest, verify, export."""

    def __init__(self, config: MemoriaConfig):
        self.config = config
        self.store = InterviewStore(config)

    def _person_dir(self, person_id: str) -> Path:
        return Path(self.config.person_dir(person_id))

    def _require_person(self, person_id: str):
        return self.store.get_person(person_id)  # raises InterviewError if missing

    # -- manifest ------------------------------------------------------------
    def build_manifest(self, person_id: str, include_media: bool = True) -> dict:
        """Checksummed inventory of the person's whole directory tree."""
        person = self._require_person(person_id)
        pdir = self._person_dir(person_id)
        entries = []
        for f in sorted(pdir.rglob("*")):
            if not f.is_file():
                continue
            if f.name == "manifest.json" or f.name.startswith("."):
                continue
            if not include_media and f.suffix.lower() in (".wav", ".mp3", ".ogg", ".flac"):
                continue
            entries.append(_file_entry(f, str(f.relative_to(pdir))))
        return {
            "manifest_version": MANIFEST_VERSION,
            "person_id": person_id,
            "person_name": person.name,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "file_count": len(entries),
            "total_bytes": sum(e["bytes"] for e in entries),
            "files": entries,
        }

    def write_manifest(self, person_id: str, include_media: bool = True) -> Path:
        manifest = self.build_manifest(person_id, include_media)
        out = self._person_dir(person_id) / "manifest.json"
        atomic_write_json(out, manifest)
        return out

    def verify(self, person_id: str) -> dict:
        """Tamper check: every file's sha256 must match the manifest.
        Added files are reported but not fatal (the archive grows)."""
        pdir = self._person_dir(person_id)
        mpath = pdir / "manifest.json"
        if not mpath.is_file():
            return {"ok": False, "error": "no manifest — write one first",
                    "missing": [], "changed": [], "added": []}
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        by_rel = {e["path"]: e for e in manifest["files"]}

        missing, changed = [], []
        ok = True
        for rel, entry in by_rel.items():
            f = pdir / rel
            if not f.is_file():
                missing.append(rel)
                ok = False
                continue
            if sha256_file(f) != entry["sha256"]:
                changed.append(rel)
                ok = False
        added = []
        for f in sorted(pdir.rglob("*")):
            if not f.is_file():
                continue
            rel = str(f.relative_to(pdir))
            if rel in by_rel or rel == "manifest.json" or f.name.startswith("."):
                continue
            added.append(rel)
        return {"ok": ok, "missing": missing, "changed": changed, "added": added,
                "report": f"{len(missing)} missing, {len(changed)} changed, "
                          f"{len(added)} added (added files are reported, not fatal)"}

    # -- exports -------------------------------------------------------------
    def export_json(self, person_id: str) -> Path:
        """Complete machine-readable bundle (answers + letters; media by path)."""
        person = self._require_person(person_id)
        bundle = {
            "format": "memoria-archive-bundle",
            "format_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "person": {"id": person.id, "name": person.name,
                       "birth_year": person.birth_year},
            "answers": [asdict(a) for a in self.store.answers(person_id)],
            "letters": [asdict(l) for l in self.store.letters(person_id)],
        }
        out = Path(self.config.exports_dir) / f"{person_id}.json"
        atomic_write_json(out, bundle)
        return out

    def export_markdown(self, person_id: str) -> Path:
        """The century file: Markdown, human-readable, forever-readable."""
        person = self._require_person(person_id)
        answers = self.store.answers(person_id)

        chapters: dict[str, list] = {}
        order: list[str] = []
        for a in answers:
            ch = _chapter_of(a.question_id)
            if ch not in chapters:
                order.append(ch)
                chapters[ch] = []
            chapters[ch].append(a)

        lines: list[str] = []
        add = lines.append
        add(f"# {person.name}")
        add("")
        add("> A record of a life, kept by memoria. "
            f"Exported {datetime.now(timezone.utc).date().isoformat()}.")
        add("> Read this file in fifty years. It needs no software.")
        add("")
        add(f"- Person id: `{person.id}`")
        if person.birth_year:
            add(f"- Birth year: {person.birth_year}")
        add(f"- Answers: {len(answers)}")
        add("")
        add("## Contents")
        for ch in order:
            title = CHAPTER_TITLES.get(ch, ch.title())
            add(f"- {title} — {len(chapters[ch])} answers")
        add("")
        for ch in order:
            title = CHAPTER_TITLES.get(ch, ch.title())
            add(f"## {title}")
            add("")
            for a in chapters[ch]:
                add(f"**{a.question_text}**")
                add("")
                add(a.text)
                add("")
        text = "\n".join(lines)
        out = Path(self.config.exports_dir) / f"{person_id}-century.md"
        atomic_write(out, text.encode("utf-8"))
        return out

    def export_all(self, person_id: str) -> dict:
        """Both exports + a fresh manifest in one call."""
        self.write_manifest(person_id)
        return {"manifest": str(self._person_dir(person_id) / "manifest.json"),
                "json": str(self.export_json(person_id)),
                "markdown": str(self.export_markdown(person_id))}
