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

Replace (the owner, 2026-11-03: the cleaning actions clear out what they
replace): the slices ticked under "Instead of" make way for the new one.
The first is rewritten as it, in place (SST, SD, PLMNs; its number stays,
so what names it keeps naming it); the tracking areas, 5QI mappings and
resource groups that named the others name it instead (a row that would
repeat one is removed), and the others are removed. The tracking areas
ticked announce it and the others stop. A 5QI two mappings would then map
for it keeps the first mapping that served the kept slice; the other's row
goes, and the mapping with it if it is left naming no slice. A resource
group left with only a replaced slice goes where the kept one has its own.

Refused: an SST or SD out of range, a slice the gNB already has (but one
being replaced), nothing to change. Noted: an AMF whose slice list
(SERVEDAMF NRPLMN_SUPPORT, what it reported at NG setup) lacks the new
slice.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, natural, why
from .links import Site, _runtime
from .qos_replace import DEFAULT_BEARER, _namers
from .tidy import PROFILES

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


def _serving(doc: Doc, gnb: str, dn: str) -> list[str]:
    return [m for m in doc.of_class("NRDRB_5QI", gnb) if not _runtime(m)
            and any(_rel(gnb, r.get("snssaiDN")) == dn for r in doc.items(m, "snssaiList"))]


def _point(doc: Doc, gnb: str, holder: str, list_name: str, field: str, olds: set, keep: str, w) -> bool:
    """The rows of a list naming one of `olds`: named `keep` instead, or removed where a row names it already."""
    rows = doc.items(holder, list_name)
    has = any(_rel(gnb, r.get(field)) == keep for r in rows)
    changed = False
    for i in reversed(range(len(rows))):
        if _rel(gnb, rows[i].get(field)) in olds:
            if has:
                doc.remove_item(holder, list_name, i, w)
            else:
                doc.set_item(holder, list_name, i, field, keep, w)
                has = True
            changed = True
    return changed


def _replace(site: Site, doc: Doc, gnb: str, replaced: list[str], sst: str, sd: Optional[str], plmns: list[str],
             tas: list[str], notes: list[str], w) -> str:
    """The first replaced slice rewritten as the new one; what named the others names it; they go."""
    keep, others = replaced[0], set(replaced[1:])
    was = site.by_dn[keep]
    for name, value in (("administrativeState", "Unlocked"), ("sst", sst), ("sd", sd)):
        now = was["p"].get(name)
        if value is None:
            if now is not None:
                doc.unset(keep, name, w(f"{_name(sst, sd)} has no SD (was {now})."))
        elif now != value:
            doc.set(keep, name, value, w(f"{label(keep)} becomes {_name(sst, sd)}" + (f" (was {now})." if now else ".")
                                         if name != "administrativeState" else
                                         "Unlocked, as every slice in the files this was built from is."))
    if [_rel(gnb, x) for x in was["simple"].get("nrPlmnDNList", [])] != plmns:
        doc.set_values(keep, "nrPlmnDNList", plmns, w("The PLMNs it is offered in."))
    moved = w(f"Named a slice this replaces; it names {label(keep)}, the new slice, instead.")
    for t in doc.of_class("TRACKINGAREA", gnb):
        if t in tas:
            _point(doc, gnb, t, "snssaiList", "snssaiDN", others, keep, moved)
            if not any(_rel(gnb, r.get("snssaiDN")) == keep for r in doc.items(t, "snssaiList")):
                doc.add_item(t, "snssaiList", [("snssaiDN", keep)], w("The tracking area announces it."))
        else:
            for i in reversed(range(len(doc.items(t, "snssaiList")))):
                if _rel(gnb, doc.items(t, "snssaiList")[i].get("snssaiDN")) in others | {keep}:
                    doc.remove_item(t, "snssaiList", i, w("The tracking area wasn't ticked: it doesn't announce the "
                                                          "slice."))
    for m in doc.of_class("NRDRB_5QI", gnb):
        _point(doc, gnb, m, "snssaiList", "snssaiDN", others, keep, moved)
    groups = [x for prof in doc.children(gnb, "NRRESOURCEGROUP_PROFILE") for x in doc.children(prof,
                                                                                               "NRRESOURCEGROUP")]
    names = {x: {_rel(gnb, r.get("resourceDN")) for r in doc.items(x, "nrResourceList")} for x in groups}
    has_own = any(keep in n for n in names.values())
    for x in groups:
        if not names[x] & others:
            continue
        if names[x] - others - {keep} or not has_own:
            _point(doc, gnb, x, "nrResourceList", "resourceDN", others, keep, moved)
            has_own = True
        else:
            doc.delete(x, w(f"The resource group of a slice this replaces; {label(keep)} has its own."))
    for o in sorted(others, key=natural):
        doc.delete(o, w(f"{label(o)} ({_name(*_key(site.by_dn[o]))}) is replaced by {label(keep)}, the new slice; "
                        "what named it names that now."))
    if others:
        notes.append(f"{label(keep)} becomes {_name(sst, sd)}; what named "
                     + ", ".join(label(o) for o in sorted(others, key=natural)) + " names it, and "
                     + ("it is" if len(others) == 1 else "they are") + " removed.")
    return keep


def _one_per_5qi(doc: Doc, gnb: str, dn: str, served: list[str], notes: list[str], w) -> None:
    """Each 5QI mapped once for the slice: the first mapping that served the kept slice keeps it."""
    by_value: dict[str, list[str]] = {}
    for m in sorted(_serving(doc, gnb, dn), key=lambda x: (x not in served, natural(x))):  # served: the kept slice's
        for v in doc.values(m, "fiveqiValueList"):
            by_value.setdefault(v, []).append(m)
    for v, ms in sorted(by_value.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        for m in ms[1:]:
            if not doc.exists(m):
                continue
            rows = doc.items(m, "snssaiList")
            for i in reversed(range(len(rows))):
                if _rel(gnb, rows[i].get("snssaiDN")) == dn:
                    doc.remove_item(m, "snssaiList", i, w(f"{label(ms[0])} maps 5QI {v} for the slice already."))
            if not doc.items(m, "snssaiList"):
                drb = _rel(gnb, doc.get(m, "nrDrbDN"))
                parts = [_rel(gnb, doc.get(drb, x)) for x in PROFILES] if drb and doc.exists(drb) else []
                doc.delete(m, w(f"It mapped 5QI {v} only for a slice this replaces, and {label(ms[0])} maps it for "
                                "the new one; naming no slice it would serve every slice."))
                gone = [m]
                for x in [drb, *parts]:  # its bearer (never NRDRB-1, the default), then its profiles
                    if not x or not doc.exists(x) or x == drb and instance(x) == DEFAULT_BEARER:
                        continue
                    if not _namers(doc, gnb)[x]:
                        doc.delete(x, w(f"Only {label(m)} used it."))
                        gone.append(x)
                notes.append(f"Removed {', '.join(label(x) for x in gone)}: {label(ms[0])} maps 5QI {v} for the "
                             "slice" + (f", and only {label(m)} used the rest." if len(gone) > 1 else "."))


def available(ctx: Context) -> Optional[str]:
    if _gnbs(ctx.site):
        return None
    return "This file has no 5G gNB (NRBTS)."


def setup(ctx: Context) -> dict:
    site = ctx.site
    gnbs, plmns, tas, maps, map_default, slices = [], {}, {}, {}, {}, {}
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
        slices[g["dn"]] = [{"value": x["dn"], "label": f"{label(x['dn'])} · {_name(*_key(x))}",
                            "details": [f"Served by {', '.join(label(m) for m in _served_by(site, g['dn'], x['dn']))}."
                                        if _served_by(site, g["dn"], x["dn"]) else "No mapping names it."]}
                           for x in _slices(site, g["dn"])]
        map_default[g["dn"]] = []
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
                     "them all unticked to take those of a slice with the same SST (or, replacing, those of the "
                     "slices it replaces)."},
            {"id": "replaces", "label": "Instead of", "type": "checks", "dependsOn": "gnb", "optionsByKey": slices,
             "defaultByKey": map_default, "optional": True,
             "hint": "The slices it replaces. The first ticked becomes the new slice in place; what named the others "
                     "names it instead, and they are removed. None ticked: it is added beside them."},
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
    replaced = [s["dn"] for s in sorted(mine, key=lambda x: natural(x["dn"])) if s["dn"] in (inputs.get("replaces")
                                                                                        or [])]
    if sst and any(_key(s) == (sst, sd) for s in mine if s["dn"] not in replaced):
        problems.append(f"{label(g)} already has {_name(sst, sd)}.")
    plmns = [p for p in (inputs.get("plmns") or []) if site.by_dn.get(p, {}).get("cls") == "NRPLMN"]
    if not plmns and site.child(g, "NRPLMN"):
        problems.append("Tick at least one PLMN to offer it in.")
    if problems:
        raise PlanError(problems)

    doc = Doc(ctx.raw)
    w = lambda reason, basis="choice": why("slice", reason, basis)
    tas = [t for t in (inputs.get("tas") or []) if site.by_dn.get(t, {}).get("cls") == "TRACKINGAREA"]
    if replaced:
        dn = _replace(site, doc, g, replaced, sst, sd, plmns, tas, notes, w)
    else:
        start = max([int(instance(s["dn"])) for s in mine if instance(s["dn"]).isdigit()] + [0]) + 1
        params = [("administrativeState", "Unlocked"), ("sst", sst)] + ([("sd", sd)] if sd is not None else [])
        dn = doc.create(g, "SNSSAI", doc.next_free(g, "SNSSAI", start), params,
                        w=w(f"{_name(sst, sd)}; Unlocked, as every slice in the files this was built from is."))
        if plmns:
            doc.set_values(dn, "nrPlmnDNList", plmns, w("The PLMNs it is offered in."))
        for t in tas:
            doc.add_item(t, "snssaiList", [("snssaiDN", dn)],
                         w("The tracking area announces it; 64 of 68 in the files this was built from list every "
                           "slice of their gNB."))

    picked = [m for m in (inputs.get("mappings") or []) if site.by_dn.get(m, {}).get("cls") == "NRDRB_5QI"
              and not any(_rel(g, r.get("snssaiDN")) == dn for r in doc.items(m, "snssaiList"))]
    twin = None
    if not picked and not (replaced and _serving(doc, g, dn)):
        twin = next((s for s in mine if s["p"].get("sst") == sst and s["dn"] not in replaced
                     and _served_by(site, g, s["dn"])), None)
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
    if replaced:
        _one_per_5qi(doc, g, dn, _served_by(site, g, replaced[0]), notes, w)
    if twin:
        notes.append(f"It gets the 5QI mappings of {label(twin['dn'])}, which has the same SST: "
                     + ", ".join(label(m) for m in picked) + ".")
    elif any(m["lists"].get("snssaiList") for m in _mappings(site, g)) and not picked and not _serving(doc, g, dn):
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
    if not replaced and mine and all(s["dn"] in groups for s in mine):
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

    count = len(mine) + 1 - len(replaced)
    if count > 8:
        notes.append(f"{label(g)} now has {count} slices. A UE asks for at most eight at a time (TS 23.501 "
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
    if not doc.changes:
        raise PlanError([f"{label(dn)} is {_name(sst, sd)} already, offered and announced as picked: nothing to "
                         "change."])
    return finish(ctx, doc, {
        "label": f"Slice {_name(sst, sd)}",
        "summary": f"{label(dn)} on {label(g)}: {_name(sst, sd)}"
                   + (f", replacing {', '.join(f'{label(x)} ({_name(*_key(site.by_dn[x]))})' for x in replaced)}"
                      if replaced and (len(replaced) > 1 or _key(site.by_dn[replaced[0]]) != (sst, sd)) else ""),
        "notes": notes,
        "confirm": [f"The AMF and SMF serve {_name(sst, sd)}, and the subscribers who use it have it in their "
                    "subscription."],
        "focus": dn,
    })
