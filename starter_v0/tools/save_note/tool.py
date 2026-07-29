from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from tools._shared import ROOT, domain, err

NOTES_DIR = ROOT / "research_notes"


def _bullet(item: dict[str, Any]) -> str:
    text = (item.get("title") or item.get("summary") or "").strip().replace("\n", " ")
    if len(text) > 200:
        text = text[:197] + "..."
    source = item.get("source") or domain(item.get("url", ""))
    url = item.get("url") or ""
    link = f" ([{source}]({url}))" if url else (f" ({source})" if source else "")
    return f"- {text}{link}"


def save_note(items: list[dict[str, Any]] | None = None, note: str = "", filename: str = "notes.md") -> dict[str, Any]:
    try:
        items = items or []
        safe_name = Path(filename).name or "notes.md"
        if not safe_name.endswith(".md"):
            safe_name += ".md"
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        path = NOTES_DIR / safe_name

        parts = [f"## {datetime.now().isoformat(timespec='seconds')}"]
        if note.strip():
            parts.append(note.strip())
        parts.extend(_bullet(item) for item in items)
        parts.append("")
        block = "\n".join(parts) + "\n"

        with path.open("a", encoding="utf-8") as file:
            file.write(block)

        return {
            "tool": "save_note",
            "path": str(path),
            "items_saved": len(items),
            "note_saved": bool(note.strip()),
        }
    except Exception as exc:
        return err("save_note", exc)
