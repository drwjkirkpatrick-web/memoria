"""Step 5: archive — manifest, tamper detection, JSON bundle, century file."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore, InterviewEngine
from memoria.archive import Archive, _chapter_of


def _make_person_with_answers(tmp_path, n_answers=6, name="Ada"):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person(name, 1948)
    eng = InterviewEngine(store, p.id)
    eng.start("starter", chapters=["roots", "joy"])
    i = 0
    while eng.current_question is not None:
        eng.answer(f"answer number {i} — some real words")
        i += 1
        if i >= n_answers:
            break
    eng.complete()
    return store, p


def test_chapter_of():
    assert _chapter_of("q_starter_roots_1") == "roots"
    assert _chapter_of("q_starter_joy_10") == "joy"
    assert _chapter_of("q_custom_ab12") == "custom"


def test_manifest_roundtrip_and_verify(tmp_path):
    store, p = _make_person_with_answers(tmp_path)
    arch = Archive(MemoriaConfig(data_dir=str(tmp_path)))
    mpath = arch.write_manifest(p.id)
    assert mpath.is_file()
    m = json.loads(mpath.read_text(encoding="utf-8"))
    assert m["person_name"] == "Ada"
    assert m["file_count"] >= 2  # person.json + records.jsonl

    v = arch.verify(p.id)
    assert v["ok"] is True
    assert v["report"].startswith("0 missing, 0 changed")


def test_tamper_detected(tmp_path):
    store, p = _make_person_with_answers(tmp_path)
    arch = Archive(MemoriaConfig(data_dir=str(tmp_path)))
    arch.write_manifest(p.id)

    # tamper: modify a file's content behind memoria's back
    rpath = Path(store.person_dir(p.id)) / "records.jsonl"
    original = rpath.read_bytes()
    rpath.write_bytes(original + b"garbage\n")

    v = arch.verify(p.id)
    assert v["ok"] is False
    assert len(v["changed"]) == 1
    assert "records.jsonl" in v["changed"]

    # delete a file: missing
    (Path(store.person_dir(p.id)) / "person.json").unlink()
    v = arch.verify(p.id)
    assert "person.json" in v["missing"]


def test_added_files_reported_not_fatal(tmp_path):
    store, p = _make_person_with_answers(tmp_path)
    arch = Archive(MemoriaConfig(data_dir=str(tmp_path)))
    arch.write_manifest(p.id)
    # a new file appears after the manifest (the archive grows)
    (Path(store.person_dir(p.id)) / "voice" / "clip.wav").parent.mkdir(exist_ok=True)
    (Path(store.person_dir(p.id)) / "voice" / "clip.wav").write_bytes(b"RIFFxxxx")
    v = arch.verify(p.id)
    assert v["ok"] is True          # growth is not tampering
    assert "voice/clip.wav" in v["added"]


def test_verify_without_manifest(tmp_path):
    store, p = _make_person_with_answers(tmp_path)
    arch = Archive(MemoriaConfig(data_dir=str(tmp_path)))
    v = arch.verify(p.id)
    assert v["ok"] is False
    assert "no manifest" in v["error"]


def test_export_json_bundle(tmp_path):
    store, p = _make_person_with_answers(tmp_path)
    arch = Archive(MemoriaConfig(data_dir=str(tmp_path)))
    out = arch.export_json(p.id)
    assert out.is_file()
    bundle = json.loads(out.read_text(encoding="utf-8"))
    assert bundle["format"] == "memoria-archive-bundle"
    assert bundle["person"]["name"] == "Ada"
    assert len(bundle["answers"]) == 6
    assert bundle["answers"][0]["text"].startswith("answer number")


def test_century_file_readable(tmp_path):
    store, p = _make_person_with_answers(tmp_path)
    arch = Archive(MemoriaConfig(data_dir=str(tmp_path)))
    out = arch.export_markdown(p.id)
    text = out.read_text(encoding="utf-8")
    # structure: title, contents, chapters, questions, answers
    assert text.startswith("# Ada")
    assert "## Contents" in text
    assert "## Roots" in text          # 5 roots answers (n_answers=6: 5 roots + 1 joy)
    assert "**Where did you grow up" in text
    assert "answer number 0" in text
    assert "needs no software" in text
    # plain UTF-8 Markdown — readable by any text editor for the next century
    text.encode("utf-8")  # must be valid UTF-8


def test_export_all_writes_three_artifacts(tmp_path):
    store, p = _make_person_with_answers(tmp_path)
    arch = Archive(MemoriaConfig(data_dir=str(tmp_path)))
    out = arch.export_all(p.id)
    assert Path(out["manifest"]).is_file()
    assert Path(out["json"]).is_file()
    assert Path(out["markdown"]).is_file()
    # and verify is green right after export
    assert arch.verify(p.id)["ok"] is True


def test_export_missing_person(tmp_path):
    arch = Archive(MemoriaConfig(data_dir=str(tmp_path)))
    with pytest.raises(Exception):
        arch.export_markdown("person_nope")
