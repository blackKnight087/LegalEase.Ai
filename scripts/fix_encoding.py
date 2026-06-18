"""Fix non-UTF-8 bytes in orchestrator modules."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for name in ("intent_engine.py", "answer_orchestrator.py"):
    p = ROOT / name
    b = p.read_bytes()
    b = b.replace(b"\x97", b"-").replace(b"\x96", b"-")
    for old, new in (
        (b"\xe2\x80\x94", b"-"),
        (b"\xe2\x80\x99", b"'"),
        (b"\xe2\x80\x9c", b'"'),
        (b"\xe2\x80\x9d", b'"'),
        (b"\xe2\x80\x93", b"-"),
    ):
        b = b.replace(old, new)
    text = b.decode("utf-8", errors="replace")
    text = text.replace("\ufffd", "-").replace("?", "-")
    text = text.replace("Source:**", "**Source:**")
    p.write_text(text, encoding="utf-8", newline="\n")
    print(f"fixed {name}")
