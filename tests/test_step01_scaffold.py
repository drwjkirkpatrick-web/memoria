"""Step 1: scaffold + data model round-trips."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.models import (Person, Question, Answer, InterviewSession,
                            Letter, VoiceSample, to_json_line, from_json_line, TIERS)
from memoria.storage import atomic_write, atomic_write_json, read_json, sha256_bytes
from memoria.config import MemoriaConfig, load_config


def test_person_create():
    p = Person.create("Walker")
    assert p.id.startswith("person_")
    assert p.name == "Walker"


def test_person_requires_name():
    try:
        Person.create("   ")
        assert False, "should have raised"
    except ValueError:
        pass


def test_all_records_round_trip():
    records = [
        Person.create("Ada"),
        Question(id="q_1", chapter="roots", text="Where did you grow up?"),
        Answer(id="a_1", person_id="person_1", question_id="q_1",
               question_text="Where did you grow up?", text="In a small coastal town."),
        InterviewSession(id="s_1", person_id="person_1"),
        Letter(id="l_1", person_id="person_1", recipient="grandchildren",
               body="When you read this..."),
        VoiceSample(id="v_1", person_id="person_1", path="/tmp/x.wav", duration_s=12.5),
    ]
    for r in records:
        line = to_json_line(r)
        rebuilt = from_json_line(line)
        assert type(rebuilt) is type(r), f"{type(r)} round-trip failed"
        assert json.loads(line)["_kind"] in ("person", "question", "answer",
                                             "session", "letter", "voice_sample")


def test_tiers_and_validation():
    for tier in TIERS:
        Answer(id="a", person_id="p", question_id="q", question_text="t",
               text="x", tier=tier)  # all valid
    for bad in ("friends", "public", ""):
        try:
            Answer(id="a", person_id="p", question_id="q", question_text="t",
                   text="x", tier=bad)
            assert False, f"tier {bad!r} should have raised"
        except ValueError:
            pass


def test_letter_open_rules():
    # executor rule ok without date
    Letter(id="l", person_id="p", recipient="r", open_rule="executor")
    # on-date requires a date
    try:
        Letter(id="l", person_id="p", recipient="r", open_rule="on-date")
        assert False, "should have raised"
    except ValueError:
        pass
    Letter(id="l", person_id="p", recipient="r", open_rule="on-date", open_date="2060-01-01")


def test_atomic_write_and_read(tmp_path):
    p = tmp_path / "deep" / "nested" / "file.json"
    atomic_write_json(p, {"hello": "world", "n": 1})
    assert read_json(p) == {"hello": "world", "n": 1}
    # overwrite works
    atomic_write_json(p, {"hello": "again"})
    assert read_json(p)["hello"] == "again"


def test_atomic_write_crash_never_tears(tmp_path):
    """A failed write must leave the original intact and no stray files."""
    p = tmp_path / "file.json"
    atomic_write_json(p, {"v": 1})
    before = read_json(p)
    try:
        atomic_write(p, None)  # bytes(None) will TypeError mid-write
    except TypeError:
        pass
    assert read_json(p) == before
    assert not list(tmp_path.glob(".tmp-*"))


def test_sha256_bytes():
    assert sha256_bytes(b"hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_config_paths(tmp_path):
    c = MemoriaConfig(data_dir=str(tmp_path))
    c.ensure_dirs()
    assert os.path.isdir(c.people_dir)
    assert c.person_dir("person_x").startswith(str(tmp_path))
    env = {"MEMORIA_DATA": str(tmp_path / "alt")}
    assert load_config(env).data_dir == str(tmp_path / "alt")


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
