"""
The site check behind GET /api/files/{f}/check: every link rule
(links.py) run on one file. Each action also runs it on its preview, so a
plan can't leave the file with a new broken link.

Pure: bytes in, dict out.
"""
from __future__ import annotations

from ..ca import _load
from .links import RULES, Site, run


def check_loaded(mos: list[dict]) -> dict:
    findings = run(Site(mos))
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] += 1
    return {
        "summary": {"errors": counts["error"], "warnings": counts["warning"], "infos": counts["info"]},
        "findings": findings,
        "rules": [{k: r[k] for k in ("id", "title", "kind", "severity", "basis", "evidence")} for r in RULES],
    }


def check_site(raw: bytes) -> dict:
    return check_loaded(_load(raw))


def new_findings(before: dict, after: dict) -> list[dict]:
    """Findings in `after` that `before` doesn't have, matched on rule and
    title, so an action's review can show what it would break."""
    seen = {(f["ruleId"], f["title"]) for f in before["findings"]}
    return [f for f in after["findings"] if (f["ruleId"], f["title"]) not in seen]
