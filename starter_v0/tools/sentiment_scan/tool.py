from __future__ import annotations

from typing import Any

from tools._shared import err, fold_text

POSITIVE_TERMS = {
    "tot", "tuyet", "thich", "an tuong", "vui", "tich cuc", "hay", "xuat sac",
    "thanh cong", "vuot troi", "an tuong", "dang mong doi", "hao hung",
    "great", "good", "love", "amazing", "excellent", "awesome", "impressive",
    "positive", "win", "winning", "best", "happy", "excited", "fantastic",
}
NEGATIVE_TERMS = {
    "te", "xau", "that vong", "kem", "tieu cuc", "buon", "gian", "lo ngai",
    "chi trich", "phan doi", "sai lam", "that bai", "khong tot",
    "bad", "terrible", "hate", "worst", "disappointing", "negative", "fail",
    "failing", "angry", "sad", "cheating", "wrong", "awful", "poor",
}


def _item_text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(field) or "") for field in ("title", "summary"))


def _classify(text: str) -> str:
    folded = fold_text(text)
    positive_hits = sum(1 for term in POSITIVE_TERMS if term in folded)
    negative_hits = sum(1 for term in NEGATIVE_TERMS if term in folded)
    if positive_hits > negative_hits:
        return "positive"
    if negative_hits > positive_hits:
        return "negative"
    return "neutral"


def sentiment_scan(items: list[dict[str, Any]] | None = None, topic: str = "") -> dict[str, Any]:
    try:
        items = items or []
        buckets: dict[str, list[dict[str, Any]]] = {"positive": [], "negative": [], "neutral": []}
        for item in items:
            label = _classify(_item_text(item))
            buckets[label].append({
                "title": item.get("title") or (item.get("summary") or "")[:80],
                "url": item.get("url"),
                "source": item.get("source"),
            })

        total = len(items)
        counts = {label: len(bucket) for label, bucket in buckets.items()}
        overall = max(counts, key=lambda label: counts[label]) if total else "neutral"

        return {
            "tool": "sentiment_scan",
            "topic": topic,
            "total_items": total,
            "counts": counts,
            "overall_sentiment": overall if total else None,
            "examples": {label: bucket[:3] for label, bucket in buckets.items()},
            "method_note": "Phan loai nhanh theo tu dien tu khoa VI+EN cuc bo, mang tinh tham khao, khong phai NLP model.",
        }
    except Exception as exc:
        return err("sentiment_scan", exc)
