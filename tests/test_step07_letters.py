"""Step 7: legacy letters — sealing, unlock rules, audit log."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.config import MemoriaConfig
from memoria.interview import InterviewStore
from memoria.letters import LetterBox, LetterError


@pytest.fixture
def env(tmp_path):
    store = InterviewStore(MemoriaConfig(data_dir=str(tmp_path)))
    p = store.create_person("Ruth", 1942)
    return store, p, str(tmp_path)


def test_write_requires_body_and_recipient(env):
    store, p, d = env
    box = LetterBox(MemoriaConfig(data_dir=d))
    with pytest.raises(LetterError):
        box.write(p.id, "grandchildren", "   ")
    with pytest.raises(LetterError):
        box.write(p.id, "  ", "Dear ones")

    l = box.write(p.id, "grandchildren", "When you are old enough, plant a garden.")
    assert l.id.startswith("ltr_")
    assert l.open_rule == "executor"  # default


def test_executor_letter_sealed_until_executor(env):
    store, p, d = env
    box = LetterBox(MemoriaConfig(data_dir=d))  # no executor key
    l = box.write(p.id, "daughter", "I was always proud of you, every single day.")
    r = box.readable(p.id, l.id)
    assert r["sealed"] is True
    assert "body" not in r          # the sealed body NEVER leaks
    assert r["recipient"] == "daughter"  # metadata visible so family knows it exists

    # executor presents the REAL key from config → opens
    box_exec = LetterBox(MemoriaConfig(data_dir=d),
                         executor_key=MemoriaConfig(data_dir=d).executor_key)
    r2 = box_exec.readable(p.id, l.id)
    assert r2["sealed"] is False
    assert r2["body"].startswith("I was always proud")
    # unlock audit logged
    unlocks = json.loads((Path(store.person_dir(p.id)) / "unlocks.jsonl").read_text().splitlines()[0])
    assert unlocks["by"] == "executor"
    assert unlocks["letter_id"] == l.id


def test_on_date_letter_opens_on_time(env):
    store, p, d = env
    box = LetterBox(MemoriaConfig(data_dir=d))
    past = box.write(p.id, "son", "Happy 40th, finally.",
                     open_rule="on-date", open_date="2020-01-01")
    future = box.write(p.id, "son", "For your 60th.",
                       open_rule="on-date", open_date="2060-01-01")

    r_past = box.readable(p.id, past.id)
    r_future = box.readable(p.id, future.id)
    assert r_past["sealed"] is False and "body" in r_past
    assert r_future["sealed"] is True and "body" not in r_future
    # the future letter never leaks through readable_all either
    allr = box.readable_all(p.id)
    assert any(x["sealed"] for x in allr)
    assert all("body" not in x for x in allr if x["sealed"])


def test_executor_cannot_open_on_date_early(env):
    """The executor key opens executor letters; it does not override dates."""
    store, p, d = env
    box = LetterBox(MemoriaConfig(data_dir=d),
                    executor_key=MemoriaConfig(data_dir=d).executor_key)
    l = box.write(p.id, "son", "For your 60th.",
                  open_rule="on-date", open_date="2060-01-01")
    r = box.readable(p.id, l.id)
    assert r["sealed"] is True


def test_letter_not_found(env):
    store, p, d = env
    box = LetterBox(MemoriaConfig(data_dir=d))
    with pytest.raises(LetterError):
        box.readable(p.id, "ltr_missing")


def test_occasion_metadata(env):
    store, p, d = env
    box = LetterBox(MemoriaConfig(data_dir=d), executor_key="k")
    l = box.write(p.id, "family", "Merry Christmas 2045.",
                  occasion="Christmas 2045", open_rule="on-date", open_date="2045-12-25")
    r = box.readable(p.id, l.id)  # sealed (future) but occasion visible
    assert r["sealed"] is True
    assert r["occasion"] == "Christmas 2045"
