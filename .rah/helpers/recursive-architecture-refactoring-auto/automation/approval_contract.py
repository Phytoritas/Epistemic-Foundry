#!/usr/bin/env python3
"""Shared approval-vocabulary contract (R12).

One placeholder set for every approval surface: fleet verdicts and ralph
review approvals must reject the same normalized filler words, so a gate
cannot be satisfied on one surface by text the other would refuse.
"""

from __future__ import annotations

import re

APPROVAL_PLACEHOLDERS = {
    "x",
    "ok",
    "okay",
    "pass",
    "passed",
    "reviewed",
    "review passed",
    "looks good",
    "lgtm",
    "done",
    "good",
    "fine",
    "n/a",
    "na",
    "none",
    "placeholder",
    "tbd",
    "todo",
    "true",
    "yes",
    "approve",
    "approved",
    # Korean filler vocabulary (reviewer round 2: "승인"/"검토 완료" passed)
    "승인",
    "승인함",
    "승인됨",
    "완료",
    "완료됨",
    "검토",
    "검토함",
    "검토됨",
    "검토 완료",
    "확인",
    "확인함",
    "확인됨",
    "통과",
    "이상 없음",
    "이상없음",
    "문제 없음",
    "문제없음",
    "좋음",
    "오케이",
    "검증",
    "검증함",
    "검증됨",
    "검증 완료",
    "테스트 통과",
    "리뷰 완료",
}

_NORMALIZE_RE = re.compile(r"[^a-z0-9가-힣 ]+")


def normalize_approval_text(value: str) -> str:
    collapsed = _NORMALIZE_RE.sub(" ", str(value or "").lower())
    return " ".join(collapsed.split())


def is_placeholder_approval(value: str) -> bool:
    normalized = normalize_approval_text(value)
    if not normalized or normalized in APPROVAL_PLACEHOLDERS:
        return True
    # Reviewer-found paddings: "approved approved", "LGTM E0001", "E0001",
    # and round 2: "LGTM E1", "approved 1234". Strip E-ID-shaped tokens of
    # ANY digit length and bare numbers, then require at least one word that
    # is neither placeholder vocabulary nor filler — an approval must say
    # something about WHAT was reviewed, not just that it was.
    without_ids = re.sub(r"\be\d+\b", " ", normalized)
    without_ids = re.sub(r"\b\d+\b", " ", without_ids)
    words = [w for w in without_ids.split() if w]
    if not words:
        return True
    placeholder_words = set()
    for phrase in APPROVAL_PLACEHOLDERS:
        placeholder_words.update(phrase.split())
    return all(word in placeholder_words for word in words)
