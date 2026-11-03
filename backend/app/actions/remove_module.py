"""
Remove a radio or baseband card, with its cables, SFPs, antenna-line links
and SYNC entry (the delete action's rules, dependents.py).

Refused while anything still runs on it: a cell whose channel mapping
names the radio's antennas, a cell listing it (frRefList, modDNList), a
CBRS registration (CBSD.rmodDN), radios cabled to the baseband card, or a
transport link on it (ETHLK.modDN). An antenna-line device left with no
link is said in the plan, not removed: the RET or TMA stays on the antenna
and can be linked to the radio that replaces this one.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from .delete import describe
from .dependents import OF_RADIO, apply_removal, plan_removal
from .doc import Doc, label, why
from .hardware import base, cables, modules
from .add_radio import _describe

ID = "remove-module"
TITLE = "Remove a radio or baseband card"
GROUP = "Hardware"
SUMMARY = "Delete a radio (RMOD) or baseband card (BBMOD) with its cables, SFPs and sync entry."
UI = "form"
KEYWORDS = "hardware RMOD BBMOD radio baseband module remove delete decommission CABLINK"


def available(ctx: Context) -> Optional[str]:
    if ctx.site.of("RMOD") or ctx.site.of("BBMOD"):
        return None
    return "This file has no radio or baseband card."


def setup(ctx: Context) -> dict:
    describe_code = _describe(ctx)
    opts = []
    for mod in modules(ctx.site):
        if mod["class"] not in ("RMOD", "BBMOD"):
            continue
        name = describe_code(mod["code"]) if mod["code"] else None
        if mod["class"] == "RMOD":
            details = [f"Cells on it: {', '.join(mod['cells'])}. Delete or move them first." if mod["cells"]
                       else "No cell uses it."]
        else:
            radios = sorted({label(c["p"]["secondEndpointDN"]) for c in cables(ctx.site, mod["dn"])
                             if "/RMOD-" in (c["p"].get("secondEndpointDN") or "")})
            details = [f"Radios cabled to it: {', '.join(radios)}." if radios else "No radio is cabled to it."]
        opts.append({"value": mod["dn"], "key": mod["dn"], "group": "Radios" if mod["class"] == "RMOD" else "Baseband cards",
                     "label": f"{mod['label']} · {mod['code'] or 'no code'}" + (f" {name}" if name else ""),
                     "details": details})
    return {
        "intro": "Deletes the module with what only makes sense with it: its cables, SFPs, antenna-line links and its "
                 "entry in the sync target list.",
        "fields": [{"id": "module", "label": "Module", "type": "select", "options": opts}],
    }


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    dn = inputs.get("module") or ""
    m = site.by_dn.get(dn)
    if not m or m["cls"] not in ("RMOD", "BBMOD"):
        raise PlanError(["Pick the radio or baseband card to remove."])
    problems = []
    if m["cls"] == "BBMOD":
        radios = sorted({c["p"]["secondEndpointDN"] for c in cables(site, dn)
                         if "/RMOD-" in (c["p"].get("secondEndpointDN") or "") and c["p"].get("firstEndpointDN") == dn})
        if radios:
            problems.append(f"{', '.join(label(r) for r in radios)} {'are' if len(radios) > 1 else 'is'} cabled to "
                            f"{label(dn)}: remove {'them' if len(radios) > 1 else 'it'} or cable "
                            f"{'them' if len(radios) > 1 else 'it'} to another card first.")
    removal = plan_removal(site, [dn])
    problems += removal.blockers
    if problems:
        raise PlanError(problems)
    doc = Doc(ctx.raw)
    apply_removal(doc, removal, lambda d, reason: why("remove-module", f"{label(dn)} and everything under it." if d == dn
                                                      else f"Goes with {label(dn)}: {reason}.", "choice"))
    notes = describe(removal, [dn])
    gone = set(removal.roots)
    for ald in site.of("ALD"):
        links = [l for l in site.of("LOGLINK") if ald["dn"] in (l["p"].get("firstEndpointDN"), l["p"].get("secondEndpointDN"))]
        if links and all(l["dn"] in gone for l in links):
            notes.append(f"{label(ald['dn'])} ({ald['p'].get('productCode') or 'an antenna-line device'}) has no link "
                         f"left. It stays: link it to the radio that replaces {label(dn)}, or delete it.")
    code = base(m["p"].get("prodCodePlanned"))
    confirm = []
    if any(site.by_dn.get(r, {}).get("cls") in OF_RADIO for r in removal.roots):
        confirm.append(f"{label(dn)} is deregistered at the SAS: the file loses its CBSD, but the SAS keeps the "
                       "registration until it is told.")
    return finish(ctx, doc, {"label": f"Remove {label(dn)}", "summary": f"{label(dn)}" + (f" ({code})" if code else "")
                             + " with its cables and links.", "notes": notes, "confirm": confirm, "focus": None})
