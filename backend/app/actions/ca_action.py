"""
The CA wizard (ca_wizard.py) as an action. It keeps its own modal
(CaWizardModal) because its pair grid doesn't fit a form; the planning is
unchanged.

Inputs: {enb, relations, ul, options, donor: {name, source}}, as the
/ca/preview endpoint has always taken.
"""
from __future__ import annotations

from ..ca_wizard import DEFAULT_OPTIONS, plan_ca, rank_donors, wizard_setup
from . import Context, PlanError
from .site_check import check_loaded, check_site, new_findings

ID = "ca"
TITLE = "Set up carrier aggregation"
GROUP = "LTE"
SUMMARY = "Pair PCells with SCells on one eNB and write the CA settings, with values from a working CA file."
UI = "ca-wizard"
KEYWORDS = "carrier aggregation CAREL CAPR scell pcell"


def available(ctx: Context):
    enbs = [m for m in ctx.mos if m["cls"] == "LNBTS"]
    if not enbs:
        return "This file has no LTE eNB (LNBTS)."
    if not any(sum(1 for c in ctx.site.child(e["dn"], "LNCEL")) >= 2 for e in enbs):
        return "CA needs at least two LTE cells on one eNB."
    return None


def _donors(ctx: Context) -> list[dict]:
    """Working CA exports, one per distinct content (the first in lookup
    order wins). The file being edited counts too: when it already runs CA,
    its own values are the best match."""
    seen, out = set(), []
    for f in ctx.corpus():
        if f["donor"] and f["sha1"] not in seen:
            seen.add(f["sha1"])
            out.append({**f["donor"], "name": f["name"], "source": f["source"],
                        "self": f["name"] == ctx.filename and f["source"] == ctx.source})
    return out


def setup(ctx: Context) -> dict:
    """Per eNB: the cells, which pairs the rules forbid and why, the current
    relations, presets, and the donor files ranked for it."""
    out = wizard_setup(ctx.raw)
    donors = _donors(ctx)
    for enb in out["enbs"]:
        ranked = rank_donors(enb, donors)
        for d in ranked:
            if d["self"]:
                d["score"] += 100
                d["reasons"].insert(0, "This file's own CA setup")
        enb["donors"] = sorted(ranked, key=lambda d: -d["score"])
    return {**out, "defaultOptions": DEFAULT_OPTIONS}


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    donor = inputs.get("donor") or {}
    if not donor.get("name") or not donor.get("source"):
        raise PlanError(["Pick a donor file."])
    try:
        donor_raw = ctx.read(donor["name"], donor["source"])
    except FileNotFoundError:
        raise PlanError([f"Donor file {donor['name']} not found."])
    new_bytes, result = plan_ca(ctx.raw, donor_raw, donor["name"], inputs, ctx.release_index())
    before, after = check_loaded(ctx.mos), check_site(new_bytes)
    result["check"] = {"before": before["summary"], "after": after["summary"], "new": new_findings(before, after)}
    result["focus"] = result["firstRelation"]
    return new_bytes, result
