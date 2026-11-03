"""
Set up DRX: turn connected-mode DRX on or off for one eNB's LTE cells or
one gNB's NR cells, as a preset, with every parameter the dictionary rules
make depend on it.

LTE (LNCEL, its DRX-0/SDRX-0 profile tables, the eNB's qciTab mapping):
  - "on": actDrx and actSmartDrx, the QCI -> DRX profile mapping the
    corpus uses (QCI 1-4, 65-67 on profile 2, voice; 5-9, 69, 70 on 3).
    Only one example site and the owner's battery experiment run LTE DRX;
    Nokia's 25R2 production files leave it off.
  - "battery": "on", plus what the owner's battery experiment changed:
    non-GBR QCIs (6-9, 70) on profile 4 (320 ms long cycle), a 256rf
    paging cycle, a 10 s inactivity timer, and shorter Smart DRX short-
    cycle timers on profiles 3-5.
  - "off": actDrx off, and the flags rule actDrx 1.1/1.4 says need it.
  The fixes the LTE18/SBTS18A rules force: a DRX and an SDRX object
  (actDrx 1.2, actSmartDrx 2), copied from a sibling cell; RI reporting
  compatible with DRX on manually allocated PUCCH (actDrx 2.4, 3.1) and
  on 1.4/3 MHz cells (2.1, 2.2); Smart DRX short cycle equal to the long
  one when actQci1eVTT is on (actSmartDrx 2.3, 2.4); and modPeriodCoeff so
  that it times the paging cycle stays within 1024 frames (defPagCyc 1.1).
  Rules with no unambiguous fix (profile priorities, eICIC timers, shared
  cell resources) refuse instead.

NR (NRBTS's NRDRX profiles, NRCELL, NRDRB); no NR dictionary exists, so
this follows the 25R2 production files, where every gNB has the same four
profiles (NoDRX, Default NonGbr, Default VoNR, Default ANR) and C-DRX on:
  - "on": the four profiles (missing ones created with the production
    values), actCDrx and actCDrxVoNR, and the cell's and bearers' profile
    references. References to a missing object, to nothing, or to NoDRX
    move to the matching default; ones to a custom profile are kept.
  - "off": actCDrx and actCDrxVoNR off.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, label, release_of, why

ID = "drx"
TITLE = "Set up DRX"
GROUP = "Cells"
SUMMARY = "Turn connected-mode DRX on or off for an eNB's or gNB's cells, with a battery-saving preset for LTE."
UI = "form"
KEYWORDS = "DRX C-DRX smart DRX battery power saving paging LNCEL NRCELL NRDRX qciTab"

# --- LTE --------------------------------------------------------------------

# QCI -> DRX profile, as in the corpus's qciTab rows (98-114 of 114 eNBs).
QCI_PROFILE = {"1": "2", "2": "2", "3": "2", "4": "2", "65": "2", "66": "2", "67": "2",
               "5": "3", "6": "3", "7": "3", "8": "3", "9": "3", "69": "3", "70": "3"}
BATTERY_QCI = {"6": "4", "7": "4", "8": "4", "9": "4", "70": "4"}
# Smart DRX profile -> drxShortCycleT, from the owner's battery experiment.
BATTERY_SHORT_CYCLE_T = {"drxSmartProfile3": "2", "drxSmartProfile4": "2", "drxSmartProfile5": "4"}

# Turned off with actDrx, because they need it (actDrx 1.1 and 1.4).
NEEDS_DRX = ("actSmartDrx", "actDrxDuringMeasGap", "actQci1RfDrx", "actForcedDrxS1Ho", "actDrxDuringTTIB")

PAGING_RF = {"32rf": 32, "64rf": 64, "128rf": 128, "256rf": 256}

LTE_PRESETS = [
    {"value": "on", "label": "DRX on (Nokia profiles)",
     "details": ["actDrx and Smart DRX on in each cell, with the cell's own DRX profile tables.",
                 "The eNB's QCI table maps voice and GBR bearers to profile 2 and data to profile 3, as most "
                 "files do."]},
    {"value": "battery", "label": "Battery saver",
     "details": ["As DRX on, plus what the battery-saving DRX experiment this was built from changed:",
                 "data bearers (QCI 6-9, 70) on profile 4, the 320 ms long cycle;",
                 "paging every 256 radio frames (2.56 s) and a 10 s inactivity timer;",
                 "shorter Smart DRX short-cycle timers on profiles 3-5."]},
    {"value": "off", "label": "DRX off",
     "details": ["actDrx off, with Smart DRX and the other options that need DRX.",
                 "This is how Nokia's 25R2 production files run LTE."]},
]

# --- NR ---------------------------------------------------------------------

_T = ("drxHarqRttTimerDl", "drxHarqRttTimerUl", "drxInactivityTimer", "drxLongCycle", "drxOnDurationTimer",
      "drxPriority", "drxRetransTimerDl", "drxRetransTimerUl")
# The four profiles of every 25R2 production gNB (78 of 82 files exactly).
NRDRX_DEFAULTS = {
    "NoDRX": dict(zip(_T, ("0symbols", "0symbols", "0ms", "10ms", "1ms", "0", "0slot", "0slot"))),
    "Default NonGbr": dict(zip(_T, ("0symbols", "0symbols", "80ms", "160ms", "10ms", "32", "0slot", "0slot"))),
    "Default VoNR": dict(zip(_T, ("0symbols", "0symbols", "20ms", "40ms", "10ms", "1", "0slot", "0slot"))),
    "Default ANR": dict(zip(_T, ("0symbols", "0symbols", "10ms", "640ms", "10ms", "16", "0slot", "0slot"))),
}
NRDRX_CLASS = "com.nokia.srbts.nrbts:NRDRX"

NR_PRESETS = [
    {"value": "on", "label": "C-DRX on (Nokia defaults)",
     "details": ["The four NRDRX profiles of the 25R2 production gNBs: NoDRX, Default NonGbr (160 ms), "
                 "Default VoNR (40 ms), Default ANR (640 ms); missing ones are added.",
                 "actCDrx and actCDrxVoNR on in each cell; data on Default NonGbr, VoNR (5QI 1) on Default VoNR, "
                 "ANR measurements on Default ANR.",
                 "References to a custom profile are kept."]},
    {"value": "off", "label": "C-DRX off",
     "details": ["actCDrx and actCDrxVoNR off in each cell. The profiles stay."]},
]


def _lte_enbs(ctx: Context) -> list[tuple[str, list[str]]]:
    out = []
    for enb in ctx.site.of("LNBTS", None):
        cells = [c["dn"] for c in ctx.site.child(enb["dn"], "LNCEL")]
        if cells:
            out.append((enb["dn"], cells))
    return out


def _nr_gnbs(ctx: Context) -> list[tuple[str, list[str]]]:
    out = []
    for gnb in ctx.site.of("NRBTS", None):
        cells = [c["dn"] for c in ctx.site.child(gnb["dn"], "NRCELL")]
        if cells:
            out.append((gnb["dn"], cells))
    return out


def _nr_supported(ctx: Context, gnb: str) -> Optional[str]:
    """None, or why the gNB's release can't take NRDRX profiles."""
    rel = release_of(ctx.site.by_dn[gnb]["version"])
    index = ctx.release_index()
    if ctx.site.child(gnb, "NRDRX") or not index:
        return None
    if "NRDRX" not in index.get(rel, {}):
        return f"No file of {rel} has NRDRX profiles, so there is no layout to follow."
    return None


def available(ctx: Context) -> Optional[str]:
    if _lte_enbs(ctx) or any(_nr_supported(ctx, g) is None for g, _ in _nr_gnbs(ctx)):
        return None
    if _nr_gnbs(ctx):
        return "This file's gNB release has no NRDRX profiles in any file, and it has no LTE cells."
    return "This file has no LTE or NR cells."


def _on(value: Optional[str]) -> bool:
    return value == "true"


def _cell_state(ctx: Context, dn: str) -> str:
    p = ctx.site.by_dn[dn]["p"]
    if ctx.site.by_dn[dn]["cls"] == "LNCEL":
        return ("Smart DRX on" if _on(p.get("actSmartDrx")) else "DRX on") if _on(p.get("actDrx")) else "DRX off"
    return "C-DRX on" if _on(p.get("actCDrx")) else "C-DRX off"


def setup(ctx: Context) -> dict:
    targets, presets, cells, left_out = [], {}, {}, []
    for dn, cs in _lte_enbs(ctx):
        on = sum(1 for c in cs if _on(ctx.site.by_dn[c]["p"].get("actDrx")))
        targets.append({"value": dn, "label": f"{label(dn)} · {len(cs)} LTE cell{'s' if len(cs) != 1 else ''}",
                        "group": "LTE eNB", "key": dn,
                        "details": [f"DRX is on in {on} of {len(cs)} cells."]})
        presets[dn] = LTE_PRESETS
        cells[dn] = [_cell_option(ctx, c) for c in cs]
    for dn, cs in _nr_gnbs(ctx):
        reason = _nr_supported(ctx, dn)
        if reason:
            left_out.append(f"{label(dn)} is left out: {reason}")
            continue
        on = sum(1 for c in cs if _on(ctx.site.by_dn[c]["p"].get("actCDrx")))
        profiles = [c["p"].get("userLabel") or label(c["dn"]) for c in ctx.site.child(dn, "NRDRX")]
        targets.append({"value": dn, "label": f"{label(dn)} · {len(cs)} NR cell{'s' if len(cs) != 1 else ''}",
                        "group": "NR gNB", "key": dn,
                        "details": [f"C-DRX is on in {on} of {len(cs)} cells.",
                                    "Profiles: " + (", ".join(profiles) if profiles else "none") + "."]})
        presets[dn] = NR_PRESETS
        cells[dn] = [_cell_option(ctx, c) for c in cs]
    intro = ("Turns connected-mode DRX on or off for the cells you pick, so UEs can sleep between bursts of traffic. "
             "Every parameter Nokia's rules make depend on DRX changes with it, and the review lists why.")
    if left_out:
        intro += " " + " ".join(left_out)
    return {
        "intro": intro,
        "fields": [
            {"id": "target", "label": "eNB or gNB", "type": "select", "options": targets,
             "default": targets[0]["value"] if len(targets) == 1 else None},
            {"id": "preset", "label": "Preset", "type": "select", "dependsOn": "target", "optionsByKey": presets},
            {"id": "cells", "label": "Cells", "type": "checks", "dependsOn": "target", "optionsByKey": cells},
        ],
    }


def _cell_option(ctx: Context, dn: str) -> dict:
    name = ctx.site.by_dn[dn]["p"].get("cellName")
    return {"value": dn, "label": label(dn) + (f" · {name}" if name else ""), "hint": _cell_state(ctx, dn)}


class _Plan:
    def __init__(self, ctx: Context, doc: Doc):
        self.ctx, self.doc = ctx, doc
        self.notes: list[str] = []
        self.problems: list[str] = []
        self.index = ctx.release_index()

    def known(self, dn: str, name: str) -> bool:
        """Whether the object may carry `name`: it already does, or some
        file of its release sets it on that class."""
        if self.doc.get(dn, name) is not None or not self.index:
            return True
        m = self.ctx.site.by_dn.get(dn)
        if m is None:
            return True
        return name in self.index.get(release_of(m["version"]), {}).get(m["cls"], set())

    def set(self, dn: str, name: str, value: str, w: dict) -> None:
        if self.known(dn, name):
            self.doc.set(dn, name, value, w)

    # --- LTE ---

    def ensure_child(self, cell: str, cls: str, rule: tuple[str, str]) -> Optional[str]:
        """The cell's DRX or SDRX object, copied from a sibling cell when
        it has none."""
        own = self.doc.children(cell, cls)
        if own:
            return own[0]
        parent = cell.rsplit("/", 1)[0]
        sources = [c for c in self.doc.of_class("LNCEL", parent) if self.doc.children(c, cls)]
        if not sources:
            self.problems.append(f"{label(cell)} has no {cls} object and no other cell of the eNB has one to copy. "
                                 f"Nokia rule {rule[0]} {rule[1]} needs it for DRX.")
            return None
        src = self.doc.children(sources[0], cls)[0]
        dst = f"{cell}/{cls}-0"
        self.doc.clone(src, dst, why("drx", f"DRX needs a {cls} object in the cell; this copies "
                                     f"{label(sources[0])}'s profile tables.", "official", rule),
                       rewrite={sources[0]: cell})
        return dst

    def lte(self, enb: str, cells: list[str], preset: str) -> None:
        doc = self.doc
        on = preset != "off"
        for cell in cells:
            p = doc.params(cell)
            if not on:
                for name in ("actDrx",) + NEEDS_DRX:
                    if p.get(name) == "true":
                        reason = "Turns DRX off." if name == "actDrx" else \
                            f"{name} needs actDrx, so it goes off with it."
                        rule = None if name == "actDrx" else ("actDrx", "1.4" if name == "actDrxDuringTTIB" else "1.1")
                        doc.set(cell, name, "false", why("drx", reason, "official" if rule else "choice", rule))
                self.pucch(cell, drx=False)
                continue
            drx = self.ensure_child(cell, "DRX", ("actDrx", "1.2"))
            sdrx = self.ensure_child(cell, "SDRX", ("actSmartDrx", "2"))
            if not drx or not sdrx:
                continue
            self.lte_rules(cell, drx, sdrx)
            self.set(cell, "actDrx", "true", why("drx", "Turns DRX on in the cell.", "choice"))
            self.set(cell, "actSmartDrx", "true", why(
                "drx", "Smart DRX on: the UE uses a short cycle right after activity, then the long one. Both "
                       "sites that run LTE DRX in the files this was built from use it.", "files"))
            self.pucch(cell, drx=True)
            if p.get("actQci1eVTT") == "true":
                for prof in ("drxSmartProfile2", "drxSmartProfile6"):
                    for i, row in enumerate(doc.items(sdrx, prof)):
                        if row.get("drxLongCycle") and row.get("drxShortCycle") != row["drxLongCycle"]:
                            doc.set_item(sdrx, prof, i, "drxShortCycle", row["drxLongCycle"], why(
                                "drx", f"actQci1eVTT is on, so {prof}'s short cycle must equal its long cycle.",
                                "official", ("actSmartDrx", "2.3" if prof.endswith("2") else "2.4")))
            if preset == "battery":
                self.battery_cell(cell, sdrx)
        if on:
            self.qci_mapping(enb, preset, cells)

    def lte_rules(self, cell: str, drx: str, sdrx: str) -> None:
        """The rules with no single right fix: refuse and say why."""
        doc = self.doc
        p = doc.params(cell)
        prio = lambda dn, prof: next((r.get("drxProfilePriority") for r in doc.items(dn, prof)), None)
        p1 = prio(drx, "drxProfile1")
        for prof in ("drxSmartProfile2", "drxSmartProfile6"):
            ps = prio(sdrx, prof)
            if p1 and ps and int(p1) <= int(ps):
                self.problems.append(f"{label(cell)}: drxProfile1's priority ({p1}) must be above {prof}'s ({ps}) "
                                     "for Smart DRX (Nokia rule actSmartDrx 2). Change one of them first.")
        if p.get("cellResourceSharingMode") not in (None, "none"):
            self.problems.append(f"{label(cell)} shares cell resources (cellResourceSharingMode "
                                 f"{p['cellResourceSharingMode']}), so DRX timers must all be above 8 (Nokia rules "
                                 "actDrx 1.3, actSmartDrx 2.1). This action doesn't check those; set DRX by hand.")
        if p.get("actEicic") == "true" and p.get("cellType") != "large":
            self.problems.append(f"{label(cell)} runs eICIC on a {p.get('cellType')} cell, which puts limits on "
                                 "the DRX inactivity timers (Nokia rules actDrx 2.3, actSmartDrx 2.2). Set DRX by "
                                 "hand.")

    def pucch(self, cell: str, drx: bool) -> None:
        """RI and CQI reporting that DRX allows (or that a small cell
        without DRX needs) on manually allocated PUCCH."""
        doc = self.doc
        for sub_cls, pucch_cls, rule_no in (("LNCEL_FDD", "MPUCCH_FDD", "2.4"), ("LNCEL_TDD", "MPUCCH_TDD", "3.1")):
            for sub in doc.children(cell, sub_cls):
                sp = doc.params(sub)
                bw = sp.get("dlChBw") if sub_cls == "LNCEL_FDD" else None
                mimo = sp.get("dlMimoMode") or ""
                for m in doc.children(sub, pucch_cls):
                    mp = doc.params(m)
                    small = bw in ("1.4 MHz", "3 MHz") and mimo in ("Closed Loop Mimo", "Dynamic Open Loop MIMO")
                    if small:
                        want = {("1.4 MHz", True): ("20ms", "1", "-1"), ("1.4 MHz", False): ("10ms", "2", "0"),
                                ("3 MHz", True): ("40ms", "1", "-1"), ("3 MHz", False): ("20ms", "2", "0")}[(bw, drx)]
                        rule = ("actDrx", ("2.1" if bw == "1.4 MHz" else "2.2") + (".2" if drx else ".1"))
                        for name, value in zip(("cqiPerNp", "riPerM", "riPerOffset"), want):
                            doc.set(m, name, value, why(
                                "drx", f"A {bw} cell with {mimo} needs {name} {value} with DRX "
                                       f"{'on' if drx else 'off'}.", "official", rule))
                    elif drx and sp.get("actAutoPucchAlloc") == "false" and mp.get("riEnable") == "true" \
                            and (mp.get("riPerM") != "1" or mp.get("riPerOffset") != "-1"):
                        for name, value in (("riPerM", "1"), ("riPerOffset", "-1")):
                            doc.set(m, name, value, why(
                                "drx", "PUCCH is allocated by hand and rank reporting is on, so DRX needs riPerM 1 "
                                       "and riPerOffset -1 (rank reports aligned with the DRX on-duration).",
                                "official", ("actDrx", rule_no)))

    def battery_cell(self, cell: str, sdrx: str) -> None:
        doc = self.doc
        p = doc.params(cell)
        self.set(cell, "defPagCyc", "256rf", why(
            "battery", "Idle UEs wake for paging every 256 radio frames (2.56 s) instead of "
                       f"{p.get('defPagCyc') or 'the default'}.", "files"))
        thresh = p.get("minInactivityTimeThresh")
        if thresh and thresh.isdigit() and int(thresh) >= 10:
            self.problems.append(f"{label(cell)}: minInactivityTimeThresh is {thresh}, and inactivityTimer must be "
                                 "above it (Nokia rule inactivityTimer 2.1), so it can't drop to 10.")
        else:
            self.set(cell, "inactivityTimer", "10", why(
                "battery", "UEs with no traffic for 10 s are released to idle, where they only wake for paging.",
                "files"))
        for sib in doc.children(cell, "SIB"):
            coeff = doc.get(sib, "modPeriodCoeff")
            if coeff and coeff.isdigit() and int(coeff) * 256 > 1024:
                doc.set(sib, "modPeriodCoeff", "4", why(
                    "battery", f"modPeriodCoeff times the paging cycle must not exceed 1024 frames; {coeff} x 256 "
                               "would. 4 x 256 keeps the system-information modification period at 1024 frames.",
                    "official", ("defPagCyc", "1.1")))
        for prof, value in BATTERY_SHORT_CYCLE_T.items():
            for i, _ in enumerate(doc.items(sdrx, prof)):
                doc.set_item(sdrx, prof, i, "drxShortCycleT", value, why(
                    "battery", "Fewer short cycles before the UE moves to the long cycle.", "files"))

    def qci_mapping(self, enb: str, preset: str, cells: list[str]) -> None:
        doc = self.doc
        want = {**QCI_PROFILE, **(BATTERY_QCI if preset == "battery" else {})}
        changed = []
        for list_name in self._lists(enb):
            if not list_name.startswith("qciTab"):
                continue
            for i, row in enumerate(doc.items(enb, list_name)):
                target = want.get(row.get("qci") or "")
                if target and row.get("drxProfileIndex") not in (None, target):
                    reason = ("Data bearers go on DRX profile 4 (320 ms long cycle)." if preset == "battery"
                              and row.get("qci") in BATTERY_QCI else
                              f"QCI {row['qci']} on DRX profile {target}, as most files map it.")
                    doc.set_item(enb, list_name, i, "drxProfileIndex", target, why(
                        "qci", reason, "files"))
                    changed.append(row["qci"])
        all_cells = doc.of_class("LNCEL", enb)
        if changed and len(cells) < len(all_cells):
            self.notes.append(f"The QCI table is the eNB's, so the new mapping (QCI {', '.join(changed)}) applies to "
                              f"all {len(all_cells)} cells of {label(enb)}, including ones you didn't pick.")

    def _lists(self, dn: str) -> list[str]:
        m = self.ctx.site.by_dn.get(dn) or {}
        return list((m.get("lists") or {}).keys())

    # --- NR ---

    def nr(self, gnb: str, cells: list[str], preset: str) -> None:
        doc = self.doc
        if preset == "off":
            for cell in cells:
                for name in ("actCDrx", "actCDrxVoNR"):
                    if doc.get(cell, name) == "true":
                        doc.set(cell, name, "false", why("drx", "Turns C-DRX off.", "choice"))
            return
        profiles = self.nr_profiles(gnb)
        nodrx = profiles["NoDRX"]
        repoint = lambda value: not value or not doc.exists(value) or value == nodrx
        kept: dict[tuple[str, str], int] = {}
        for cell in cells:
            self.set(cell, "actCDrx", "true", why("drx", "Turns C-DRX on for data.", "choice"))
            self.set(cell, "actCDrxVoNR", "true", why("drx", "Turns C-DRX on for VoNR calls.", "choice"))
            for name, prof in (("nonGbrNrDrxDN", "Default NonGbr"), ("voNRNrDrxDN", "Default VoNR")):
                value = doc.get(cell, name)
                if repoint(value) and self.known(cell, name):
                    doc.set(cell, name, profiles[prof], why(
                        "drx", f"{'Data' if name.startswith('non') else 'VoNR'} uses the {prof} profile, as on the "
                               "production gNBs" + ("" if not value else f" (was {self._what(value)})") + ".", "files"))
                elif value != profiles[prof]:
                    kept[(name, self._what(value))] = kept.get((name, self._what(value)), 0) + 1
            # The release index has scalars only, so a list is known when this
            # cell or another one in the file has it.
            rows = doc.items(cell, "drxProfileNrAnr")
            has_list = rows or any(doc.items(c, "drxProfileNrAnr") for c in doc.of_class("NRCELL", gnb))
            if has_list and (not rows or any(repoint(r.get("nrDrxDN")) for r in rows)):
                for i in reversed(range(len(rows))):
                    doc.remove_item(cell, "drxProfileNrAnr", i, why("drx", "Replaced below.", "files"))
                doc.add_item(cell, "drxProfileNrAnr", [("drxControl", "any"), ("nrDrxDN", profiles["Default ANR"])],
                             why("drx", "ANR measurements use the Default ANR profile (640 ms), as on the production "
                                        "gNBs.", "files"))
        for (name, what), n in kept.items():
            self.notes.append(f"{n} cell{'s keep' if n != 1 else ' keeps'} {name} on {what}, a profile of this file's "
                              "own; the preset leaves it.")
        for name in ("actDedicatedAnrDrxProfile", "actSaIntraFreqAnrDrxProf"):
            self.set(gnb, name, "true", why(
                "drx", "Lets ANR measurements use their own DRX profile; on in every production gNB.", "files"))
        self.nr_bearers(gnb, profiles, repoint)

    def _what(self, dn: str) -> str:
        if not self.doc.exists(dn):
            return f"{label(dn)}, which doesn't exist"
        return self.doc.get(dn, "userLabel") or label(dn)

    def nr_profiles(self, gnb: str) -> dict[str, str]:
        """userLabel -> NRDRX distName for the four defaults, adding the
        missing ones with the production values."""
        doc = self.doc
        found = {}
        for dn in doc.children(gnb, "NRDRX"):
            lab = doc.get(dn, "userLabel")
            if lab in NRDRX_DEFAULTS and lab not in found:
                found[lab] = dn
        version = self.ctx.site.by_dn[gnb]["version"]
        for i, (lab, values) in enumerate(NRDRX_DEFAULTS.items()):
            if lab in found:
                continue
            taken = {dn.rsplit("-", 1)[-1] for dn in doc.children(gnb, "NRDRX")}
            inst = str(i) if str(i) not in taken else doc.next_free(gnb, "NRDRX", 0).rsplit("-", 1)[-1]
            found[lab] = doc.create(gnb, "NRDRX", inst, [("userLabel", lab), *values.items()],
                                    full_class=NRDRX_CLASS, version=version,
                                    w=why("drx", f"The {lab} profile of the production gNBs.", "files"))
        return found

    def nr_bearers(self, gnb: str, profiles: dict[str, str], repoint) -> None:
        """Each bearer's profile: Default VoNR for the one only 5QI 1
        (conversational voice) uses, Default NonGbr for the rest."""
        doc = self.doc
        users: dict[str, set] = {}
        for q in doc.children(gnb, "NRDRB_5QI"):
            target = doc.get(q, "nrDrbDN")
            if target:
                users.setdefault(target, set()).add(q.rsplit("-", 1)[-1])
        for drb in doc.children(gnb, "NRDRB"):
            value = doc.get(drb, "nrDrxDN")
            prof = "Default VoNR" if users.get(drb) == {"1"} else "Default NonGbr"
            if repoint(value) and self.known(drb, "nrDrxDN"):
                doc.set(drb, "nrDrxDN", profiles[prof], why(
                    "drx", f"{'The VoNR bearer (5QI 1)' if prof == 'Default VoNR' else 'A data bearer'} uses "
                           f"{prof}" + ("" if not value else f" (was {self._what(value)})") + ".", "files"))


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    target = inputs.get("target")
    lte = dict(_lte_enbs(ctx))
    nr = dict(_nr_gnbs(ctx))
    if target not in lte and target not in nr:
        raise PlanError(["Pick an eNB or gNB."])
    presets = LTE_PRESETS if target in lte else NR_PRESETS
    preset = inputs.get("preset")
    if preset not in {p["value"] for p in presets}:
        raise PlanError(["Pick a preset."])
    all_cells = lte.get(target) or nr.get(target)
    picked = inputs.get("cells")
    cells = [c for c in all_cells if picked is None or c in picked]
    if not cells:
        raise PlanError(["Pick at least one cell."])
    if target in nr and (reason := _nr_supported(ctx, target)):
        raise PlanError([reason])

    doc = Doc(ctx.raw)
    p = _Plan(ctx, doc)
    (p.lte if target in lte else p.nr)(target, cells, preset)
    if p.problems:
        raise PlanError(p.problems)
    name = next(x["label"] for x in presets if x["value"] == preset)
    confirm = []
    if preset != "off":
        confirm.append("The UEs and services at this site can take DRX's added latency: a sleeping UE answers new "
                       "downlink data at its next on-duration.")
    if preset == "battery":
        confirm.append("Paging every 2.56 s is acceptable: calls to an idle UE can take up to about 2.5 s longer "
                       "to reach it.")
    first = next((c for c in doc.changes if c["op"] != "delete"), None)
    return finish(ctx, doc, {
        "label": f"DRX on {label(target)}: {name}",
        "summary": f"{name} on {len(cells)} cell{'s' if len(cells) != 1 else ''} of {label(target)}",
        "notes": p.notes,
        "confirm": confirm,
        "focus": first["id"] if first else None,
    })
