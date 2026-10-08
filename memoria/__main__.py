"""python -m memoria — CLI entry point."""
import sys

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        _help()
        return 0
    cmd = argv[0]
    if cmd == "version":
        print(__import__("memoria").__version__)
        return 0
    print(f"unknown command: {cmd}")
    _help()
    return 2

def _help():
    print("memoria — a digital gravestone")
    print("usage: python -m memoria <command> [args]")
    print("  interview   guided interview (built in step 3)")
    print("  version     print version")

if __name__ == "__main__":
    raise SystemExit(main())
