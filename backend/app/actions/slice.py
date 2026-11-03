"""
Add a network slice (S-NSSAI) to a gNB: an SNSSAI with its SST and
optional SD, the PLMNs it is offered in, the tracking areas that announce
it, and the 5QI mappings that serve it.

What the files do (PROJECT_STATE §9.9):
  - SNSSAI-n under NRBTS: administrativeState Unlocked (192 of 192), sst,
    sd where set (93), nrPlmnDNList naming the gNB's NRPLMNs (all of them
    on 193 of 205 slices).
  - Every TRACKINGAREA lists every slice of its gNB in snssaiList (64 of
    68).
  - NRDRB_5QI snssaiList names the slices a 5QI mapping serves; one that
    names none serves all (155 mappings). Where mappings name slices, a
    new slice gets the mappings of a slice with the same SST, so each 5QI
    is still mapped once per slice (the qos-unique rule).

3GPP: TS 23.501 §5.15.2: an S-NSSAI is an SST and an optional SD;
Table 5.15.2.2-1 standardises SST 1 eMBB, 2 URLLC, 3 MIoT, 4 V2X and 5
HMTC. TS 38.331 S-NSSAI: sst is 8 bits, sst-SD 32 (SST and a 24-bit SD).
Read from the ETSI PDFs of V17.10.0 and V17.6.0 when this was built. At
most eight S-NSSAIs go in an Allowed or Requested NSSAI (TS 23.501
§5.15.2.1), which the note on a ninth slice repeats.

Where every slice has its own resource group (NRRESOURCEGROUP under
NRRESOURCEGROUP_PROFILE, nrResourceList naming it: the 27 production
gNBs), the new slice gets one with the quotas of a slice of its SST. The
minimum scheduler quotas of those gNBs' groups add up to 95 of 100; a new
group's is cut to what is left.

Refused: an SST or SD out of range, a slice the gNB already has. Noted:
an AMF whose slice list (SERVEDAMF NRPLMN_SUPPORT, what it reported at NG
setup) lacks the new slice.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, why
from .links import Site, _runtime

ID = "slice"
TITLE = "Add a network slice"
GROUP = "Features"
SUMMARY = "An S-NSSAI on a gNB, in its PLMNs and tracking areas, with the 5QI mappings that serve it."
UI = "form"
KEYWORDS = "slice S-NSSAI SNSSAI SST SD eMBB URLLC MIoT V2X network slicing TRACKINGAREA NRDRB_5QI"

SST = {"1": "eMBB", "2": "URLLC", "3": "MIoT", "4": "V2X", "5": "HMTC"}


def _gnbs(site: Site) -> list[dict]:
    return [m for m in site.of("NRBTS") if not _runtime(m["dn"])]


def _slices(site: Site, gnb: str) -> list[dict]:
    return [m for m in site.child(gnb, "SNSSAI") if not _runtime(m["dn"])]


def _key(m: dict) -> tuple[str, Optional[str]]:
    return m["p"].get("sst"), m["p"].get("sd")


def _name(sst: str, sd: Optional[str]) -> str:
    return f"SST {sst}" + (f" ({SST[sst]})" if sst in SST else "") + (f", SD {sd}" if sd not in (None, "") else "")


def _mappings(site: Site, gnb: str) -> list[dict]:
    return [m for m in site.of("NRDRB_5QI", gnb) if not _runtime(m["dn"])]


def _served_by(site: Site, gnb: str, slice_dn: str) -> list[str]:
    return [m["dn"] for m in _mappings(site, gnb)
            if any(_rel(gnb, r.get("snssaiDN")) == slice_dn for r in m["lists"].get("snssaiList", []))]


def _rel(gnb: str, dn: Optional[str]) -> Optional[str]:
    """A slice reference as a full distName (one lab export writes them
    relative to the gNB)."""
    if dn and not dn.startswith("MRBTS-"):
        return f"{gnb}/{dn}"
    return dn


def available(ctx: Context) -> Optional[str]:
    if _gnbs(ctx.site):
        return None
    return "This file has no 5G gNB (NRBTS)."


def setup(ctx: Context) -> dict:
    site = ctx.site
    gnbs, plmns, tas, maps, map_default = [], {}, {}, {}, {}
    for g in _gnbs(site):
        have = ", ".join(_name(*_key(s)) for s in _slices(site, g["dn"])) or "no slice yet"
        gnbs.append({"value": g["dn"], "key": g["dn"], "label": f"{label(g['dn'])} · {have}"})
        plmns[g["dn"]] = [{"value": p["dn"], "label": f"{label(p['dn'])} · {p['p'].get('mcc')}-{p['p'].get('mnc')}"}
                          for p in site.child(g["dn"], "NRPLMN")]
        tas[g["dn"]] = [{"value": t["dn"], "label": f"{label(t['dn'])} · TAC {t['p'].get('fiveGsTac')}"}
                        for t in site.child(g["dn"], "TRACKINGAREA")]
        # Mappings that name no slice serve every slice already; only the others are a choice.
        maps[g["dn"]] = [{"value": m["dn"], "label": f"{label(m['dn'])} · 5QI {', '.join(m['simple'].get('fiveqiValueList', []))}"
                          + f" · for {', '.join(label(_rel(g['dn'], r.get('snssaiDN')) or '') for r in m['lists'].get('snssaiList', []))}"}
                         for m in _mappings(site, g["dn"]) if m["lists"].get("snssaiList")]
    return {
        "intro": "Adds an S-NSSAI to a gNB. It is offered in the PLMNs and announced in the tracking areas you tick; "
                 "the core (AMF, SMF) must serve it too.",
        "fields": [
            {"id": "gnb", "label": "gNB", "type": "select", "options": gnbs,
             "default": gnbs[0]["value"] if len(gnbs) == 1 else None},
            {"id": "sst", "label": "Slice/Service type (SST)", "type": "combo",
             "options": [{"value": k, "label": f"{k} · {v}", "group": "Standardised (TS 23.501 Table 5.15.2.2-1)"}
                         for k, v in SST.items()],
             "placeholder": "0-255"},
            {"id": "sd", "label": "Slice differentiator (SD)", "type": "text", "optional": True,
             "placeholder": "None",
             "hint": "A decimal number (0-16777215), as the files write it. Tells apart slices of one SST."},
            {"id": "plmns", "label": "Offered in", "type": "checks", "dependsOn": "gnb", "optionsByKey": plmns},
            {"id": "tas", "label": "Announced in", "type": "checks", "dependsOn": "gnb", "optionsByKey": tas},
            {"id": "mappings", "label": "5QI mappings that serve it", "type": "checks", "dependsOn": "gnb",
             "optionsByKey": maps, "optional": True, "default": [],
             "hint": "Only the mappings that name their slices are listed; the others serve every slice. Leave "
                     "them all unticked to take those of a slice with the same SST."},
        ],
    }


def _number(text: str, top: int, what: str) -> tuple[Optional[str], Optional[str]]:
    t = (text or "").strip()
    if not t:
        return None, None
    if not t.isdigit() or int(t) > top:
        return None, f"{t!r} isn't an {what} (0-{top})."
    return str(int(t)), None


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    gnb = site.by_dn.get(inputs.get("gnb") or "")
    if not gnb or gnb["cls"] != "NRBTS":
        raise PlanError(["Pick the gNB."])
    g = gnb["dn"]
    problems, notes = [], []
    sst, p1 = _number((inputs.get("sst") or "").split("·")[0], 255, "SST")
    sd, p2 = _number(inputs.get("sd") or "", 16777215, "SD")
    if p1 or not sst:
        problems.append((p1 or "Enter the SST.") + " TS 38.331 gives it 8 bits.")
    if p2:
        problems.append(p2 + " TS 38.331 gives the SD 24 bits.")
    mine = _slices(site, g)
    if sst and any(_key(s) == (sst, sd) for s in mine):
        problems.append(f"{label(g)} already has {_name(sst, sd)}.")
    plmns = [p for p in (inputs.get("plmns") or []) if site.by_dn.get(p, {}).get("cls") == "NRPLMN"]
    if not plmns and site.child(g, "NRPLMN"):
        problems.append("Tick at least one PLMN to offer it in.")
    if problems:
        raise PlanError(problems)

    doc = Doc(ctx.raw)
    w = lambda reason, basis="choice": why("slice", reason, basis)
    start = max([int(instance(s["dn"])) for s in mine if instance(s["dn"]).isdigit()] + [0]) + 1
    params = [("administrativeState", "Unlocked"), ("sst", sst)] + ([("sd", sd)] if sd is not None else [])
    dn = doc.create(g, "SNSSAI", doc.next_free(g, "SNSSAI", start), params,
                    w=w(f"{_name(sst, sd)}; Unlocked, as every slice in the files this was built from is."))
    if plmns:
        doc.set_values(dn, "nrPlmnDNList", plmns, w("The PLMNs it is offered in."))
    for t in (inputs.get("tas") or []):
        if site.by_dn.get(t, {}).get("cls") == "TRACKINGAREA":
            doc.add_item(t, "snssaiList", [("snssaiDN", dn)],
                         w("The tracking area announces it; 64 of 68 in the files this was built from list every "
                           "slice of their gNB."))

    picked = [m for m in (inputs.get("mappings") or []) if site.by_dn.get(m, {}).get("cls") == "NRDRB_5QI"]
    twin = None
    if not picked:
        twin = next((s for s in mine if s["p"].get("sst") == sst and _served_by(site, g, s["dn"])), None)
        picked = _served_by(site, g, twin["dn"]) if twin else []
    # One 5QI is mapped once per slice.
    seen: dict[str, str] = {}
    for m in picked:
        for v in site.by_dn[m]["simple"].get("fiveqiValueList", []):
            if v in seen and seen[v] != m:
                raise PlanError([f"5QI {v} would be mapped for the new slice by both {label(seen[v])} and "
                                 f"{label(m)}; tick one of them."])
            seen[v] = m
    because = f", as it serves {label(twin['dn'])} (the same SST)" if twin else ""
    for m in picked:
        doc.add_item(m, "snssaiList", [("snssaiDN", dn)], w(f"Serves the new slice{because}."))
    if twin:
        notes.append(f"It gets the 5QI mappings of {label(twin['dn'])}, which has the same SST: "
                     + ", ".join(label(m) for m in picked) + ".")
    elif any(m["lists"].get("snssaiList") for m in _mappings(site, g)) and not picked:
        open_ = [m for m in _mappings(site, g) if not m["lists"].get("snssaiList")]
        notes.append("The gNB's 5QI mappings name the slices they serve and none serves this one"
                     + (f"; only {', '.join(label(m['dn']) for m in open_)}, which name no slice, will." if open_
                        else ": its PDU sessions get no bearer until one does."))

    # Resource groups: where every slice has its own (production: NRRESOURCEGROUP_PROFILE-0, one group per slice).
    groups = {}
    for prof in site.child(g, "NRRESOURCEGROUP_PROFILE"):
        for grp in site.child(prof["dn"], "NRRESOURCEGROUP"):
            for r in grp["lists"].get("nrResourceList", []):
                groups[_rel(g, r.get("resourceDN"))] = grp
    if mine and all(s["dn"] in groups for s in mine):
        like = twin["dn"] if twin else next((s["dn"] for s in mine if s["p"].get("sst") == sst), mine[0]["dn"])
        model = groups[like]
        prof = model["dn"].rsplit("/", 1)[0]
        used = sum(int((x["lists"].get("schedulerParams") or [{}])[0].get("minQuota") or 0)
                   for x in site.child(prof, "NRRESOURCEGROUP"))
        sched = dict((model["lists"].get("schedulerParams") or [{}])[0])
        rac = dict((model["lists"].get("racParams") or [{}])[0])
        want = int(sched.get("minQuota") or 0)
        if want > 100 - used:
            sched["minQuota"] = str(max(0, 100 - used))
            notes.append(f"{label(model['dn'])}'s minimum scheduler quota is {want}, but the groups of "
                         f"{label(prof)} already guarantee {used} of 100, so the new one gets {sched['minQuota']}. "
                         "Lower another group's to give this slice more.")
        gdn = doc.create(prof, "NRRESOURCEGROUP", doc.next_free(prof, "NRRESOURCEGROUP"), [],
                         w=w(f"A resource group for the slice, as every slice of {label(g)} has; its quotas are "
                             f"{label(model['dn'])}'s, the group of {label(like)}."))
        doc.add_item(gdn, "nrResourceList", [("resourceDN", dn)], w("The group's slice."))
        if rac:
            doc.add_item(gdn, "racParams", sorted(rac.items()), w("Admission quotas, as the model group's."))
        if sched:
            doc.add_item(gdn, "schedulerParams", sorted(sched.items()), w("Scheduler quotas."))
        notes.append(f"It gets its own resource group, {label(gdn)}, with {label(model['dn'])}'s quotas.")

    if len(mine) + 1 > 8:
        notes.append(f"{label(g)} now has {len(mine) + 1} slices. A UE asks for at most eight at a time (TS 23.501 "
                     "§5.15.2.1: at most eight S-NSSAIs in a Requested or Allowed NSSAI).")
    lacking = []
    for amf in site.of("SERVEDAMF", g):
        for sup in site.child(amf["dn"], "NRPLMN_SUPPORT"):
            have = {(r.get("sst"), r.get("sd")) for r in sup["lists"].get("snssaiAMFList", [])}
            if have and (sst, sd) not in have:
                lacking.append(f"{amf['p'].get('amfName') or label(amf['dn'])} ({sup['p'].get('mcc')}-"
                               f"{sup['p'].get('mnc')}: {', '.join(_name(a, b) for a, b in sorted(have, key=str))})")
    if lacking:
        notes.append("At NG setup the AMF reported the slices it serves, and this one isn't among them: "
                     + "; ".join(lacking) + ". It works once the AMF serves it.")
    return finish(ctx, doc, {
        "label": f"Slice {_name(sst, sd)}",
        "summary": f"{label(dn)} on {label(g)}: {_name(sst, sd)}",
        "notes": notes,
        "confirm": [f"The AMF and SMF serve {_name(sst, sd)}, and the subscribers who use it have it in their "
                    "subscription."],
        "focus": dn,
    })
