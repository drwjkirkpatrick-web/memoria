"""Step 19: keeper operations — backup/restore round-trip, verify, dedupe."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine
from memoria.keeper import (backup, restore, verify_all, dedupe_media,
                            migration_runbook, KeeperError)
from memoria.voice_capture import MockRecorder
from memoria.voicebank import Voicebank


def _full_archive(tmp_path, with_media=True):
    cfg = MemoriaConfig(data_dir=str(tmp_path))
    store = InterviewStore(cfg)
    p = store.create_person("Ruth", 1942)
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots"])
    eng.answer("I grew up on a farm outside Salem.", tier="FAMILY")
    eng.pause()
    if with_media:
        vb = Voicebank(cfg, MockRecorder())
        vb.record_script_line(p.id, 0, seconds=5.0)
    from memoria.archive import Archive
    Archive(cfg).write_manifest(p.id)
    return cfg, p


def test_backup_creates_dated_tar(tmp_path):
    cfg, p = _full_archive(tmp_path)
    out = backup(cfg)
    assert out.is_file()
    assert out.name.startswith("memoria-backup-")
    assert out.suffixes == [".tar", ".gz"]
    # contains the data dir
    import tarfile
    with tarfile.open(out) as tar:
        names = tar.getnames()
    assert any("person.json" in n for n in names)
    assert any("records.jsonl" in n for n in names)


def test_backup_one_person(tmp_path):
    cfg, p = _full_archive(tmp_path)
    store2 = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p2 = store2.create_person("Second")
    out = backup(cfg, person_id=p.id)
    import tarfile
    with tarfile.open(out) as tar:
        names = tar.getnames()
    assert any(p.id in n for n in names)
    assert not any(p2.id in n for n in names)


def test_restore_roundtrip(tmp_path):
    cfg, p = _full_archive(tmp_path)
    out = backup(cfg)
    # restore into a clean dir
    dest = tmp_path.parent / "memoria-restore-test"
    if dest.exists():
        import shutil; shutil.rmtree(dest)
    r = restore(cfg, str(out), dest_data_dir=str(dest))
    assert r["ok"] is True
    assert r["people"] == 1
    # the restored archive actually contains the person and their answer
    store_r = InterviewStore(MemoriaConfig(data_dir=str(dest)))
    people = store_r.list_people()
    assert len(people) == 1 and people[0].name == "Ruth"
    answers = store_r.answers(people[0].id)
    assert len(answers) == 1 and "farm" in answers[0].text
    # and the manifest verifies clean
    v = verify_all(MemoriaConfig(data_dir=str(dest)))
    assert v[people[0].id]["ok"] is True


def test_restore_refuses_nonempty(tmp_path):
    cfg, p = _full_archive(tmp_path)
    out = backup(cfg)
    with pytest.raises(KeeperError):
        restore(cfg, str(out), dest_data_dir=str(tmp_path))  # not empty


def test_verify_all(tmp_path):
    cfg, p = _full_archive(tmp_path)
    v = verify_all(cfg)
    assert p.id in v and v[p.id]["ok"] is True


def test_dedupe_media(tmp_path):
    cfg, p = _full_archive(tmp_path)
    # record the same synthetic clip twice (identical MockRecorder output)
    vb = Voicebank(cfg, MockRecorder())
    vb.record_script_line(p.id, 1, seconds=5.0)
    vb.record_script_line(p.id, 2, seconds=5.0)  # same freq/amp -> identical bytes
    d = dedupe_media(cfg, person_id=p.id)
    assert d["files_deduped"] >= 1
    # dedupe is idempotent
    d2 = dedupe_media(cfg, person_id=p.id)
    assert d2["files_deduped"] == 0


def test_runbook_content():
    rb = migration_runbook()
    assert "Century files" in rb
    assert "tar.gz" in rb
    assert "Restoring onto new hardware" in rb
    assert "executor key" in rb.lower()
