"""python -m memoria — CLI entry point."""
from __future__ import annotations
import argparse
import json
import sys


def _cmd_version(args):
    from memoria import __version__
    print(__version__)
    return 0


def _cmd_packs(args):
    from memoria.config import load_config
    from memoria.packs import list_packs
    cfg = load_config()
    for p in list_packs(data_dir=cfg.data_dir):
        print(f"{p[\'id\']:<12} {p[\'questions\']:>3} questions  {p[\'source\']:<7}  {p[\'name\']}")


def _cmd_people(args):
    from memoria.config import load_config
    from memoria.interview import InterviewStore
    store = InterviewStore(load_config())
    people = store.list_people()
    if not people:
        print("no people yet — start an interview with \'memoria interview\'")
        return 0
    for p in people:
        n = len(store.answers(p.id))
        print(f"{p.id}  {p.name}  ({n} answers)")


def _cmd_interview(args):
    from memoria.config import load_config
    from memoria.interview import InterviewStore, InterviewEngine, InterviewError
    store = InterviewStore(load_config())

    person = None
    for p in store.list_people():
        if p.id == args.person or p.name.lower() == args.person.lower():
            person = p
            break
    if person is None:
        person = store.create_person(args.person, args.birth_year)

    engine = InterviewEngine(store, person.id)

    # resume the latest paused session if asked
    if args.resume:
        sess = store.latest_session(person.id)
        if sess is None:
            print("no session to resume")
            return 1
        engine.resume(sess.id)
        print(f"resumed {sess.id}")
    else:
        engine.start(args.pack, chapters=args.chapters or None)
        print(f"session {engine.session.id} — {len(engine.session.question_ids)} questions")
    print()

    # the loop
    while engine.current_question is not None:
        q = engine.current_question
        answered, total = engine.progress
        print(f"[{answered+1}/{total}] ({q.chapter}) {q.text}")
        if q.follow_ups:
            print("   follow-ups: " + " | ".join(q.follow_ups))
        try:
            text = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            engine.pause()
            print("\n[paused — resume later with --resume]")
            return 0
        if not text:
            print("   (empty — skipped)")
            engine.skip()
            continue
        engine.answer(text, tier=args.tier)
        print()

    s = engine.complete()
    print(engine.summary())
    print("interview complete — every answer saved.")
    return 0


def _cmd_export(args):
    from memoria.config import load_config
    from memoria.archive import Archive
    Archive(load_config()).export_markdown(args.person)
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(prog="memoria",
                                 description="memoria — a digital gravestone")
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("version", help="print version")
    p.set_defaults(func=_cmd_version)

    p = sub.add_parser("packs", help="list question packs")
    p.set_defaults(func=_cmd_packs)

    p = sub.add_parser("people", help="list people")
    p.set_defaults(func=_cmd_people)

    p = sub.add_parser("interview", help="guided interview")
    p.add_argument("--person", required=True, help="person id or name")
    p.add_argument("--birth-year", type=int, default=None)
    p.add_argument("--pack", default="starter")
    p.add_argument("--chapters", nargs="*", default=None,
                   help="limit to these chapters (e.g. roots love)")
    p.add_argument("--tier", default="PRIVATE", choices=["PUBLIC", "FAMILY", "PRIVATE"])
    p.add_argument("--resume", action="store_true", help="resume latest paused session")
    p.set_defaults(func=_cmd_interview)

    p = sub.add_parser("export", help="export a person's century file (markdown)")
    p.add_argument("--person", required=True)
    p.set_defaults(func=_cmd_export)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
