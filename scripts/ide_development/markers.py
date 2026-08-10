"""Managed marker block helpers (AGENTS.md style)."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ConflictError


@dataclass(frozen=True)
class MarkerParts:
    before: str
    managed: str
    after: str
    had_markers: bool


def extract_marker_block(text: str, begin: str, end: str) -> MarkerParts:
    begin_count = text.count(begin)
    end_count = text.count(end)
    if begin_count == 0 and end_count == 0:
        return MarkerParts(before=text, managed="", after="", had_markers=False)
    if begin_count != 1 or end_count != 1:
        raise ConflictError(
            "Managed marker pair is missing or corrupted",
            details={
                "beginCount": begin_count,
                "endCount": end_count,
                "begin": begin,
                "end": end,
            },
        )
    start = text.find(begin)
    stop = text.find(end)
    if start < 0 or stop < 0 or stop < start:
        raise ConflictError(
            "Managed marker pair is ordered incorrectly",
            details={"begin": begin, "end": end},
        )
    managed_start = start + len(begin)
    before = text[:start]
    managed = text[managed_start:stop]
    after = text[stop + len(end) :]
    # Nested marker detection inside managed region
    if begin in managed or end in managed:
        raise ConflictError(
            "Nested managed markers are not allowed",
            details={"begin": begin, "end": end},
        )
    return MarkerParts(before=before, managed=managed, after=after, had_markers=True)


def strip_outer_markers(body: str, begin: str, end: str) -> str:
    text = body
    if text.startswith(begin):
        text = text[len(begin) :]
        if text.startswith("\n"):
            text = text[1:]
    if text.rstrip().endswith(end):
        # remove trailing end marker
        idx = text.rfind(end)
        text = text[:idx]
        if text.endswith("\n"):
            pass
    return text


def render_marker_file(
    existing: str | None,
    managed_body: str,
    begin: str,
    end: str,
) -> str:
    """Return full file text with managed region upserted."""
    body = strip_outer_markers(managed_body, begin, end)
    # Normalize managed body to start/end with newline boundaries for stability
    if body and not body.startswith("\n"):
        body = "\n" + body
    if body and not body.endswith("\n"):
        body = body + "\n"
    block = f"{begin}{body}{end}"

    if existing is None or existing == "":
        return block + "\n"

    parts = extract_marker_block(existing, begin, end)
    if not parts.had_markers:
        # Append managed block after consumer content
        prefix = existing
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        return prefix + "\n" + block + "\n"

    before = parts.before
    after = parts.after
    # Preserve surrounding newlines reasonably
    return f"{before}{block}{after}"
