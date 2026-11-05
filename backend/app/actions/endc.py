"""
Set up EN-DC (LTE-NR dual connectivity, NSA option 3X) on one side of the
link: the 4G side (the LTE eNB, the master node) or the 5G side (the gNB,
the secondary node). Each side is checked against a template and gets
everything it lacks: an object the feature needs and the file doesn't have
is added, one it has is set to the template (the owner's rule, 2026-11-04:
"you add EVERYTHING it needs"). The review (shown as manual steps first)
is the list of what changes, to load or to enter by hand in the WebUI.

The template is what the files show for a working setup, with the
dictionary's rules on top. Evidence: the 11 production xL25R2 SRAN eNBs
with EN-DC on (all agree unless noted), the owner's lab eNBs (10, xL25R2
and TL18SP), and the 27 production 25R2 gNBs.

4G side (eNB):
  - LNBTS actLteNrDualConnectivity true (feature LTE4088). Its rules: it
    can't be on with actSatBackhaul (1.1, refused); it needs
    tLteNrDualConnectPrep (1.2; 500 ms where missing, as production; the
    lab uses 2000) and an NRDCDPR (1.2); on FDD actProSeComm must be false
    (2.1).
  - qciTab6-9 lteNrDualConnectSupport EN-DC with nrPdcpProfIdx 1001 (all
    21 EN-DC eNBs); the profile it names, pdcpProf1001, must exist (its
    rule), with production's values where it doesn't. A QCI row the eNB
    lacks is added first, from another file's row for that QCI (the QoS
    action's LTE side). QCI 5 is disabled on every working EN-DC eNB (IMS
    signalling stays on LTE): an EN-DC-eligible QCI 5 is turned back.
  - NRDCDPR-0: dlPathlossChg, tPeriodicPhr and tProhibitPhr (every NRDCDPR
    in the tool), plus what this release's files write on it.
  - NRMEASDPR-0 with one nrQuantityConfig (19 of 21), and per NR carrier an
    ENDCDMEASCONF under NRDCDPR: the B1 measurement that triggers EN-DC
    (all 11 production eNBs). The carrier is the SSB's NR-ARFCN, band and
    subcarrier spacing, from a gNB in this file or the tool
    (sites.ssb_arfcn) or typed in. Its SMTC (ssbPeriodicity sf20-r15,
    ssbDuration sf2, ssbOffset 0) is production's and must match the gNB's
    SSB burst. Where no file of the eNB's release shows the place, the B1
    measurement goes on the NRDCDPR itself, where Nokia's SBTS 18A
    dictionary has carrierFreqNrCell and the B1 thresholds.
  - X2 to the gNB: automatic (actEndcAutoX2Setup and actUeBasedAnrNr true,
    as the 11 production eNBs: the eNB learns NR cells from UEs and sets X2
    up itself), or a planned LNADJGNB (as the lab, endc_gnb), or left as it
    is.
  Every template parameter goes through the release filter: on a class
  some file of the eNB's release has, it is written only where one of
  them writes it. A class no file of the release has is still added, with
  all the template's values, and the plan says so (`_Side.guessed`). The
  template's own release (xL25R2) is exempt: the template is that
  release's evidence, whether or not its files are loaded. A to-do
  (`todo`) is left only for what no file can tell: X2 by automatic setup
  on a release none of whose files has it.

5G side (gNB):
  - X2-C and X2-U planes (NRBTS x2Cplane, x2Uplane): 79 of 86 gNBs have
    them, every one on the address its other planes use; with no other
    plane, on the address the SRAN eNB's C-plane uses, or the BTS's only
    one. A gNB with no address at all is refused: its transport comes
    first (Transport, IP interface).
  - Per cell, an NRPLMNSET_NSA (all 130 production cells: notReserved,
    configuredEpsTac 0), with its SA set's PLMNs, or, for a cell with no
    PLMN set (the lab's), the gNB's NRPLMNs. A gNB whose PLMN is its own
    mcc and mnc (23R1, no NRPLMN) has nothing to add.
  - QCI 6-9 bearers (NRDRB_QCI): production maps QCI 5-9 to NRDRB-5..9 and
    profiles of their own. A missing one is added with production's
    template, through the QoS action (qos._plan_nr).

Both sides in one run (run.py): the 4G side also sets up its gNB's 5G side
in that gNB's file ("The gNB's file": the gNB the X2 link goes to, else the
nearest one whose cells carry the NR carrier picked), and the 5G side the
4G side of each eNB picked ("Also set up the 4G side on"), measuring this
gNB's first carrier with a planned X2 link to it.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from . import qos
from .doc import Doc, instance, label, natural, release_of, why
from .endc_gnb import _Plan as _AdjPlan
from .endc_gnb import _existing, _taken
from .endc_gnb import _gnb as _endc_gnb
from .endc_gnb import _sources as _gnb_sources
from .links import Site
from .neighbours import anr_budget, far, from_text, group, lte_enbs, nearby, number, sources
from .sites import nr_cell, x2_address
from .transport import lte_cplane

ID = "endc"
TITLE = "Set up EN-DC"
GROUP = "Features"
SUMMARY = "Check one side of EN-DC (NSA) against the template, and add what it lacks: the 4G eNB or the 5G gNB."
UI = "form"
KEYWORDS = "EN-DC ENDC NSA option 3X dual connectivity 5G NR LTE4088 B1 NRDCDPR ENDCDMEASCONF qciTab template steps"

MANUAL = "manual"
KEEP, AUTO = "keep", "auto"

# 4G template (values of the 11 production xL25R2 eNBs with EN-DC on).
TEMPLATE_RELEASE = "xL25R2"  # what the template was built from: its classes and values hold there as they are
GNB_RELEASE = qos.TEMPLATE_RELEASE  # the 5G side's template: the 27 production 25R2 gNBs
T_PREP = "500"
QCIS = (6, 7, 8, 9)
ALSO_SPLIT = (69, 70)  # EN-DC-eligible on 11 of the 13 working EN-DC eNBs, not on all: not in the template
PDCP_PROFILE = "1001"
PDCP_1001 = [("pdcpProfileId", "1001"), ("pi2TargetDelay", "700"), ("pi2TargetSize", "35"),
             ("pi2Variant", "PI2 queue management disabled"), ("snSizeDl", "18bit"), ("snSizeUl", "18bit"),
             ("statusRepReq", "0"), ("tDiscard", "300ms")]
NRDCDPR = [("actSortBcListEnDc", "false"), ("bufTrigForB1Nr", "disabled"), ("dlPathlossChg", "3 db"),
           ("enDCpMaxEUTRApowerOffset", "0"), ("enDCpMaxNRpowerOffset", "0"), ("tPeriodicPhr", "50sf"),
           ("tProhibitPhr", "0sf")]
NRDCDPR_CORE = {"dlPathlossChg", "tPeriodicPhr", "tProhibitPhr"}  # on every NRDCDPR in the tool
NRMEASDPR = [("measGapEnabledNRMeas", "FR1AndFR2"), ("retryTimerB1NR", "30"), ("supervisionTimerB1NR", "2")]
NR_QUANTITY = [("filterCoefficientRsrp", "fc4"), ("filterCoefficientRsrq", "fc4"), ("filterCoeffRsrpRSIndex", "fc4"),
               ("filterCoeffRsrqRSIndex", "fc4"), ("quantityConfigId", "1")]
B1 = [("b1NrBeamReportQuantity", "RSRP"), ("b1NrBeamThreshRsrp", "41"), ("b1NrMaxNumBeams", "6"),
      ("b1NrMeasPurpose", "EN-DC and EN-DC steering"), ("b1NrReportAmount", "r2"), ("b1NrReportInterval", "1024ms"),
      ("b1ThresholdNrRsrp", "41"), ("b1TimeToTriggerRsrp", "80ms"), ("b1TriggerQuantity", "RSRP"),
      ("endcNrDropThresh", "3"), ("endcNrDropThreshTimer", "0s"), ("endcNrDropWaitTimer", "0"),
      ("hysB1ThresholdRsrp", "4"), ("nrCarPrio", "8"), ("nrPciNbrRelAddHyst", "650"), ("nrPciNbrRelAddThresh", "30"),
      ("nrPciNbrRelRemThresh", "1000000"), ("ssbDuration", "sf2"), ("ssbOffset", "0"),
      ("ssbPeriodicity", "sf20-r15")]
AUTO_X2 = [("actEndcAutoX2Setup", "true"), ("actUeBasedAnrNr", "true")]
NO_ENDC = {"5": "disabled"}  # what every working EN-DC eNB has on these QCIs
B1_CORE = {"carrierFreqNrCell", "ssbSubcarrierSpacing", "b1TriggerQuantity", "b1ThresholdNrRsrp"}  # no default
SCS = ("15kHz", "30kHz", "120kHz", "240kHz")

# 5G template.
X2_PLANES = ("x2Cplane", "x2Uplane")
OTHER_PLANES = ("ngCplane", "xnCplane", "s1Uplane", "ngUplane", "xnUplane")


def _gnbs(site: Site) -> list[dict]:
    return [m for m in site.of("NRBTS") if m["dn"].count("/") == 1]


def _carriers_of(site: Site, gnb: dict) -> list[tuple[str, str, str]]:
    seen = []
    for c in site.child(gnb["dn"], "NRCELL"):
        x = nr_cell(site, gnb, c)
        key = (x["ssb"], x["band"], x["scs"])
        if all(key) and key not in seen:
            seen.append(key)
    return seen


def _carrier_value(ssb: str, band: str, scs: str) -> str:
    return f"nr:{ssb}:{band}:{scs}"


def _carrier_label(ssb: str, band: str, scs: str) -> str:
    return f"NR-ARFCN {ssb} · n{band} · {scs.replace('kHz', ' kHz')} SCS"


def _measured(site: Site, enb: dict) -> set[str]:
    return ({m["p"].get("carrierFreqNrCell") for m in site.of("ENDCDMEASCONF", enb["dn"])}
            | {m["p"].get("carrierFreqNrCell") for m in site.child(enb["dn"], "NRDCDPR")}) - {None}


def available(ctx: Context) -> Optional[str]:
    if lte_enbs(ctx.site) or _gnbs(ctx.site):
        return None
    return "This file has neither an LTE eNB with cells nor a 5G gNB."


def setup(ctx: Context) -> dict:
    site = ctx.site
    enbs, gnbs = lte_enbs(site), _gnbs(site)
    sides = ([{"value": "4g", "key": "4g", "label": "4G side: the LTE eNB (master node)",
               "details": ["Turns EN-DC on, with the QCIs, profiles and the B1 measurement of the NR carrier it "
                           "needs, and the X2 link to the gNB."]}] if enbs else []) + \
            ([{"value": "5g", "key": "5g", "label": "5G side: the gNB (secondary node)",
               "details": ["The X2 planes, and the NSA PLMN set of each cell."]}] if gnbs else [])
    enb_opts = []
    carriers, carrier_default, x2s, x2_default = {}, {}, {}, {}
    gnb_found = _gnb_sources(ctx)
    index = ctx.release_index()
    for enb in enbs:
        dn = enb["dn"]
        on = enb["p"].get("actLteNrDualConnectivity") == "true"
        enb_opts.append({"value": dn, "key": dn, "label": f"{label(dn)} · eNB {instance(dn)}"
                         + (f" · {enb['p']['enbName']}" if enb["p"].get("enbName") else ""),
                         "details": ["EN-DC is on (actLteNrDualConnectivity)." if on else "EN-DC is off."]})
        opts, seen = [], set()
        measured = _measured(site, enb)
        if measured:
            opts.append({"value": KEEP, "key": KEEP, "group": "Already measured",
                         "label": f"Keep what it measures (NR-ARFCN {', '.join(sorted(measured))})",
                         "details": ["No new carrier: the eNB already has a B1 measurement for these."]})
        for g in gnbs:
            for key in _carriers_of(site, g):
                if key not in seen:
                    seen.add(key)
                    opts.append({"value": _carrier_value(*key), "key": _carrier_value(*key), "group": "This file's gNB",
                                 "label": _carrier_label(*key) + f" · gNB {instance(g['dn'])}",
                                 "details": [f"The SSB of gNB {instance(g['dn'])}'s cells, from its "
                                             "gscnOrSsPbchArfcn (3GPP TS 38.104)."]})
        for e in gnb_found:
            for c in e["cells"]:
                key = (c.get("ssb"), c.get("band"), c.get("scs"))
                if all(key) and key not in seen:
                    seen.add(key)
                    opts.append({"value": _carrier_value(*key), "key": _carrier_value(*key),
                                 "group": "Sites in the tool", "label": _carrier_label(*key) + f" · gNB {e['id']}",
                                 "details": [f"The SSB of gNB {e['id']}'s cells, from {e['file']}."]})
        opts.append({"value": MANUAL, "key": MANUAL, "group": "By hand", "label": "Enter the NR carrier by hand",
                     "details": ["The SSB's NR-ARFCN, the band and the SSB subcarrier spacing."]})
        carriers[dn] = opts
        carrier_default[dn] = next((o["value"] for o in opts if o["value"] == KEEP or o.get("group") == "This file's gNB"),
                                   None)
        adj = site.child(dn, "LNADJGNB")
        auto = enb["p"].get("actEndcAutoX2Setup") == "true"
        x2 = []
        if adj or auto:
            planned = ", ".join(f"{label(m['dn'])} to {m['p'].get('cPlaneIpAddr')}" for m in adj)
            x2.append({"value": KEEP, "key": KEEP, "label": "Leave X2 as it is",
                       "details": [" ".join(x for x in (f"Planned: {planned}." if adj else "",
                                                        "Automatic X2 setup is on." if auto else "") if x)]})
        rel = release_of(enb["version"])
        if not auto and (not index or rel == TEMPLATE_RELEASE
                         or "actEndcAutoX2Setup" in index.get(rel, {}).get("LNBTS", set())):
            x2.append({"value": AUTO, "key": AUTO, "label": "Automatic X2 setup, as the production SRAN sites",
                       "details": ["actEndcAutoX2Setup and actUeBasedAnrNr: the eNB learns the NR cells from UE "
                                   "measurements and sets up X2 to their gNB itself."]})
        for e in nearby(site, lte_cplane(site, dn, None), gnb_found):
            if e["ip"] and not any((m["p"].get("cPlaneIpAddr") or "").lower() == e["ip"].lower() for m in adj):
                x2.append({"value": e["key"], "key": e["key"],
                           "group": "Planned link to a gNB " + ("on this site's subnet" if e.get("subnet") else
                                                                 "in the tool"),
                           "label": f"gNB {e['id']}" + (f" {e['name']}" if e.get("name") else "") + f" · {e['ip']}",
                           "details": [f"An LNADJGNB to it, from {e['file']}. Its cell relations: the Add a "
                                       "neighbour gNB action, or UE-based ANR."]
                           + ([f"Its address is on this site's subnet ({e['subnet']}), as a co-sited BTS's is."]
                              if e.get("subnet") else [])})
        x2s[dn] = x2
        x2_default[dn] = KEEP if (adj or auto) else None
    gnb_opts = [{"value": g["dn"], "key": g["dn"], "label": f"{label(g['dn'])} · gNB {instance(g['dn'])}"
                 + (f" · {g['p'].get('btsName')}" if g["p"].get("btsName") else "")} for g in gnbs]
    enb_found = sources(ctx, "enbs", lambda e: not e["cells"], ("id", "plmn", "ip", "cells")) if gnbs else []
    enb_picks = {g["dn"]: [{"value": e["key"], "group": group(e), "hint": from_text(e),
                            "label": f"eNB {e['id']}" + (f" {e['name']}" if e.get("name") else "")
                            + (f" · {e['ip']}" if e.get("ip") else "")}
                           for e in nearby(site, x2_address(site, g), enb_found)] for g in gnbs}
    four, five, manual = {"field": "side", "equals": "4g"}, {"field": "side", "equals": "5g"}, \
        {"field": "carrier", "equals": MANUAL}
    return {
        "intro": "Checks the side you pick against the EN-DC template (what the working EN-DC files have, and "
                 "the dictionary's rules) and lists only what is missing. Load it, or copy the manual steps into "
                 "the WebUI.",
        "view": "steps",
        "fields": [
            {"id": "side", "label": "Which side", "type": "select", "options": sides,
             "default": sides[0]["value"] if len(sides) == 1 else None},
            {"id": "enb", "label": "This eNB", "type": "select", "showIf": four, "options": enb_opts,
             "default": enb_opts[0]["value"] if len(enb_opts) == 1 else None},
            {"id": "carrier", "label": "NR carrier to measure (B1)", "type": "select", "showIf": four,
             "dependsOn": "enb", "optionsByKey": carriers, "defaultByKey": carrier_default},
            {"id": "ssb", "label": "SSB NR-ARFCN", "type": "text", "showIf": manual, "placeholder": "502110"},
            {"id": "band", "label": "NR band", "type": "text", "showIf": manual, "placeholder": "41"},
            {"id": "scs", "label": "SSB subcarrier spacing", "type": "select", "showIf": manual,
             "options": [{"value": s, "label": s.replace("kHz", " kHz")} for s in SCS], "default": "30kHz"},
            {"id": "x2", "label": "X2 to the gNB", "type": "select", "showIf": four, "dependsOn": "enb",
             "optionsByKey": x2s, "defaultByKey": x2_default},
            {"id": "gnb", "label": "This gNB", "type": "select", "showIf": five, "options": gnb_opts,
             "default": gnb_opts[0]["value"] if len(gnb_opts) == 1 else None},
            {"id": "also5g", "label": "The gNB's file", "type": "checks", "showIf": four, "optional": True,
             "options": [{"value": ALSO, "label": "Set up the gNB's 5G side in its own file too",
                          "hint": "The gNB the X2 link goes to, else the one the NR carrier comes from, written with "
                                  "this one (a read-only file goes into a copy). Not for a carrier typed in."}]},
            {"id": "enbs", "label": "Also set up the 4G side on", "type": "picks", "showIf": five,
             "dependsOn": "gnb", "optionsByKey": enb_picks, "optional": True, "default": [],
             "hint": "Each eNB, in its own file, measures this gNB's carrier and gets a planned X2 link to it."},
        ],
    }


ALSO = "5g"
OTHER = {"4g": "Run it on the gNB's file too, 5G side.", "5g": "Run it on the eNB's file too, 4G side."}


def _partner(ctx: Context, inputs: dict) -> Optional[str]:
    """The gNB a 4G side pairs with: the one its X2 link goes to (a planned
    link picked, else one of the eNB's LNADJGNBs), else the nearest one in the
    tool whose cells carry the NR carrier picked (or one it already measures)."""
    if far(inputs.get("x2")):
        return inputs["x2"]
    value = (inputs.get("carrier") or "").split(":")
    enb = next((m for m in lte_enbs(ctx.site) if m["dn"] == inputs.get("enb")), None)
    if not enb:
        return None
    measured = _measured(ctx.site, enb)

    def carries(e: dict) -> bool:
        if len(value) == 4 and value[0] == "nr":
            return any((c.get("ssb"), c.get("band"), c.get("scs")) == tuple(value[1:]) for c in e["cells"])
        return value == [KEEP] and any(c.get("ssb") in measured for c in e["cells"])

    # Another export of a gNB at an address the eNB has for another gNB id is stale.
    found = [e for e in nearby(ctx.site, lte_cplane(ctx.site, enb["dn"], None), _gnb_sources(ctx))
             if carries(e) and not _taken(ctx.site, enb, e)]
    return next((e["key"] for e in found if _existing(ctx.site, enb, e["ip"], e["id"], e["plmn"])), None) or \
        next((e["key"] for e in found), None)


def legs(ctx: Context, inputs: dict) -> list[dict]:
    """The run's other side: the gNB's 5G side in its file, or each picked
    eNB's 4G side in its own, paired with this gNB."""
    if inputs.get("side") == "4g":
        there = far(_partner(ctx, inputs)) if ALSO in (inputs.get("also5g") or []) else None
        return [{"file": there[0], "action": ID, "inputs": {"side": "5g", "gnb": there[1]},
                 "what": f"gNB {instance(there[1])}'s 5G side", "settles": list(OTHER.values())}] if there else []
    gnb = next((m for m in _gnbs(ctx.site) if m["dn"] == inputs.get("gnb")), None)
    carriers = _carriers_of(ctx.site, gnb) if gnb and inputs.get("side") == "5g" else []
    out = []
    for k in dict.fromkeys(inputs.get("enbs") or []) if carriers else []:
        there = far(k)
        if there:
            out.append({"file": there[0], "action": ID,
                        "inputs": {"side": "4g", "enb": there[1], "carrier": _carrier_value(*carriers[0]),
                                   "x2": f"{ctx.key}|{gnb['dn']}"},
                        "what": f"eNB {instance(there[1])}'s 4G side, with gNB {instance(gnb['dn'])}",
                        "settles": list(OTHER.values())})
    return out


class _Side:
    """Template checks for one side: what is in place, and changes for the rest."""

    def __init__(self, ctx: Context, doc: Doc, node: dict, template: str = TEMPLATE_RELEASE):
        self.ctx, self.doc, self.site, self.node = ctx, doc, ctx.site, node
        self.template = template
        self.release = release_of(node["version"])
        self.index = ctx.release_index()
        self.ready: list[str] = []
        self.notes: list[str] = []
        self.todo: list[str] = []  # needed, but nothing tells the plan what to write
        self.made: dict[str, int] = {}
        self.guessed: set[str] = set()  # classes no file of the release has, added anyway

    def shown(self, cls: str) -> bool:
        """Some file of this release has the class (always, in the template's own)."""
        return not self.index or self.release == self.template or cls in self.index.get(self.release, {})

    def written(self, cls: str, params: list[tuple[str, str]], core: set[str] = frozenset()) -> list[tuple[str, str]]:
        """The template parameters this release's files write on the class
        (all of them in the template's own release, and on a class no file
        of the release has)."""
        if not self.shown(cls):
            self.guessed.add(cls)
            return params
        if not self.index or self.release == self.template:
            return params
        names = self.index.get(self.release, {}).get(cls, set())
        return [(k, v) for k, v in params if k in names or k in core]

    def guessed_note(self) -> None:
        if self.guessed:
            self.notes.append(f"No file of {self.release or 'this release'} loaded has "
                              f"{', '.join(sorted(self.guessed))}: written as the {self.template} template has "
                              f"{'it' if len(self.guessed) == 1 else 'them'}, with all its values. Check the release "
                              "loads them.")

    def set(self, dn: str, name: str, value: str, reason: str, basis: str = "files", rule=None) -> None:
        if (self.site.by_dn.get(dn) or {}).get("p", {}).get(name) == value:
            self.ready.append(f"{name} {value}")
            return
        self.doc.set(dn, name, value, why("endc", reason, basis, rule))

    def create(self, parent: str, cls: str, start: int, params: list[tuple[str, str]], reason: str,
               basis: str = "files") -> str:
        inst = self.doc.next_free(parent, cls, start)
        first = not self.doc.of_class(cls)
        info = self.doc.class_info(self.node["cls"])  # a new class takes the eNB's or gNB's namespace
        full = f"{info[0].rsplit(':', 1)[0]}:{cls}" if first and info and ":" in info[0] else None
        dn = self.doc.create(parent, cls, inst, params, full_class=full,
                             version=self.node["version"] if first else None, w=why("endc", reason, basis))
        self.made[cls] = self.made.get(cls, 0) + 1
        return dn


def _carrier(inputs: dict) -> Optional[tuple[str, str, str]]:
    value = inputs.get("carrier") or ""
    if value == KEEP:
        return None
    if value == MANUAL:
        problems: list[str] = []
        ssb = number(inputs.get("ssb"), 0, 3279165, "The SSB NR-ARFCN", problems)
        band = number(inputs.get("band"), 1, 512, "The NR band", problems)
        scs = inputs.get("scs") if inputs.get("scs") in SCS else None
        if not scs:
            problems.append("Pick the SSB subcarrier spacing.")
        if problems:
            raise PlanError(problems)
        return ssb, band, scs
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != "nr":
        raise PlanError(["Pick the NR carrier the eNB should measure."])
    return parts[1], parts[2], parts[3]


def _params_of(ctx: Context, cls: str) -> set[str]:
    """The parameters the knowledge base has on a class (the files' and
    the dictionaries')."""
    cat = ctx.kb.get("catalog") or {}
    return set(((cat.get("classes") or cat).get(cls) or {}).get("params") or ())


def _plan_4g(ctx: Context, doc: Doc, inputs: dict) -> tuple[dict, _Side, str]:
    site = ctx.site
    enb = next((m for m in lte_enbs(site) if m["dn"] == inputs.get("enb")), None)
    if not enb:
        raise PlanError(["Pick this file's eNB."])
    if enb["p"].get("actSatBackhaul") == "true":
        raise PlanError(["Satellite backhaul is on (actSatBackhaul): EN-DC can't be on with it "
                         "(actLteNrDualConnectivity rule 1.1). Turn it off first, if the site has no satellite link."])
    carrier = _carrier(inputs)
    x2 = inputs.get("x2") or ""
    if not x2:
        raise PlanError(["Pick how the eNB gets its X2 link to the gNB."])
    s = _Side(ctx, doc, enb)
    dn = enb["dn"]
    lists = enb.get("lists") or {}
    s.set(dn, "actLteNrDualConnectivity", "true", "Turns EN-DC on (LTE4088, LTE-NR Dual Connectivity Option 3X).",
          "official", ("actLteNrDualConnectivity", None))
    if enb["p"].get("tLteNrDualConnectPrep"):
        s.ready.append(f"tLteNrDualConnectPrep {enb['p']['tLteNrDualConnectPrep']}")
    else:
        s.set(dn, "tLteNrDualConnectPrep", T_PREP, f"Must be set with EN-DC on; {T_PREP} as on the 11 production eNBs "
                                                   "with EN-DC (the lab uses 2000).", "official",
              ("actLteNrDualConnectivity", "1.2"))
    for fdd in site.child(dn, "LNBTS_FDD"):
        if fdd["p"].get("actProSeComm") == "true":
            s.set(fdd["dn"], "actProSeComm", "false", "ProSe can't be on with EN-DC on an FDD eNB.", "official",
                  ("actLteNrDualConnectivity", "2.1"))
    if lists.get(f"pdcpProf{PDCP_PROFILE}"):
        s.ready.append(f"pdcpProf{PDCP_PROFILE}")
    else:
        doc.add_item(dn, f"pdcpProf{PDCP_PROFILE}", PDCP_1001,
                     why("endc", f"The PDCP profile the EN-DC QCIs name (nrPdcpProfIdx {PDCP_PROFILE}), which must "
                                 "exist; production's values.", "official", ("nrPdcpProfIdx", None)))
        s.notes.append(f"pdcpProf{PDCP_PROFILE} is new, with the production eNBs' values: check its fields exist in "
                       f"{s.release or 'this release'}.")
    done = []
    for x in QCIS:
        rows = lists.get(f"qciTab{x}") or []
        if rows:
            row = rows[0]
        else:
            donor = qos.qci_donor(ctx, enb, str(x), prefer=lambda row: row.get("lteNrDualConnectSupport") == "EN-DC")
            if not donor:
                s.todo.append(f"Add QCI {x} to the eNB's QCI table (qciTab{x}), EN-DC-eligible with nrPdcpProfIdx "
                              f"{PDCP_PROFILE}: no file in the tool has a qciTab{x} to take its settings from.")
                continue
            # The QoS action's LTE side adds the row; its EN-DC fields are this action's.
            out = qos._plan_lte(ctx, doc, enb, {"value": str(x), "template": donor})
            s.notes += [n for n in out["notes"] if not n.startswith("EN-DC settings")]
            row = {}
        if row.get("lteNrDualConnectSupport") == "EN-DC" and row.get("nrPdcpProfIdx"):
            done.append(str(x))
            continue
        w = why("endc", f"QCI {x} bearers may use EN-DC, with PDCP profile {PDCP_PROFILE}, as on every EN-DC eNB "
                        "this was built from.", "official", ("nrPdcpProfIdx", None))
        doc.set_item(dn, f"qciTab{x}", 0, "lteNrDualConnectSupport", "EN-DC", w)
        if not row.get("nrPdcpProfIdx"):
            doc.set_item(dn, f"qciTab{x}", 0, "nrPdcpProfIdx", PDCP_PROFILE, w)
    if done:
        s.ready.append(f"QCI {', '.join(done)} EN-DC")
    # Another QCI the file already makes EN-DC-eligible needs its profile too (rule 1.2.1).
    for name, rows in sorted(lists.items()):
        x = name[6:]
        if not (name.startswith("qciTab") and x.isdigit() and int(x) not in QCIS and rows):
            continue
        if rows[0].get("lteNrDualConnectSupport") == "EN-DC" and x in NO_ENDC:
            doc.set_item(dn, name, 0, "lteNrDualConnectSupport", NO_ENDC[x],
                         why("endc", f"QCI {x} is {NO_ENDC[x]} for EN-DC on every working EN-DC eNB in the files this "
                                     "was built from" + (": they keep IMS signalling on LTE" if x == "5" else "")
                                     + ". It was EN-DC here.", "files"))
            continue
        if rows[0].get("lteNrDualConnectSupport") == "EN-DC" and not rows[0].get("nrPdcpProfIdx"):
            doc.set_item(dn, name, 0, "nrPdcpProfIdx", PDCP_PROFILE,
                         why("endc", f"QCI {x} is EN-DC-eligible already, so it needs a PDCP profile.", "official",
                             ("actLteNrDualConnectivity", "1.2.1")))
            if int(x) not in ALSO_SPLIT:
                s.notes.append(f"QCI {x} is EN-DC-eligible in this file, and on no working EN-DC eNB in the files this "
                               "was built from" + (" (they keep IMS signalling on LTE)" if x == "5" else "")
                               + ": check that's intended.")
    nrdcdpr = site.child(dn, "NRDCDPR")
    if nrdcdpr:
        dpr = nrdcdpr[0]["dn"]
        s.ready.append(label(dpr))
    else:
        dpr = s.create(dn, "NRDCDPR", 0, s.written("NRDCDPR", NRDCDPR, NRDCDPR_CORE),
                       "The EN-DC default profile, which must exist with EN-DC on (actLteNrDualConnectivity rule 1.2); "
                       "production's values.")
    quantity = None
    meas = site.child(dn, "NRMEASDPR")
    if meas:
        s.ready.append(label(meas[0]["dn"]))
        rows = (meas[0].get("lists") or {}).get("nrQuantityConfig") or []
        quantity = rows[0].get("quantityConfigId") if rows else None
    else:
        m = s.create(dn, "NRMEASDPR", 0, s.written("NRMEASDPR", NRMEASDPR),
                     "NR measurement defaults for the B1 measurement, as on 19 of the 21 EN-DC eNBs this was built from.")
        doc.add_item(m, "nrQuantityConfig", NR_QUANTITY, why("endc", "The filtering the B1 measurement uses.", "files"))
        quantity = dict(NR_QUANTITY)["quantityConfigId"]
    if carrier:
        ssb, band, scs = carrier
        if ssb in _measured(site, enb):
            s.ready.append(f"B1 measurement of NR-ARFCN {ssb}")
        elif s.shown("ENDCDMEASCONF"):
            params = s.written("ENDCDMEASCONF", B1 + [("carrierFreqNrCell", ssb), ("ssbSubcarrierSpacing", scs)]
                               + ([("quantityConfigId", quantity)] if quantity else []),
                               {"carrierFreqNrCell", "ssbSubcarrierSpacing"})
            m = s.create(dpr, "ENDCDMEASCONF", 0, sorted(params),
                         f"The B1 measurement of the NR carrier at NR-ARFCN {ssb} (band n{band}, {scs} SSB): UEs "
                         "report it and the eNB adds the NR cell. Production's thresholds and SMTC.")
            doc.add_item(m, "freqBandIndicatorNrL", [("freqBandIndicatorNr", band), ("priority", "1")],
                         why("endc", f"The carrier's band, n{band}.", "files"))
            s.notes.append(f"The B1 measurement's SMTC (ssbPeriodicity sf20-r15, ssbDuration sf2, ssbOffset 0) is "
                           f"production's: it must match the SSB burst of the gNB at NR-ARFCN {ssb}.")
        else:
            # No file of the release has an ENDCDMEASCONF: on the NRDCDPR, as the 18A dictionary has it.
            on = _params_of(ctx, "NRDCDPR") | B1_CORE
            shown = "carrierFreqNrCell" in s.index.get(s.release, {}).get("NRDCDPR", set())
            b1 = [(k, v) for k, v in B1 + [("carrierFreqNrCell", ssb), ("ssbSubcarrierSpacing", scs)] if k in on]
            for k, v in sorted(s.written("NRDCDPR", b1, B1_CORE)):
                s.set(dpr, k, v, f"The B1 measurement of the NR carrier at NR-ARFCN {ssb} (band n{band}, {scs} SSB), "
                                 "on the NRDCDPR, where Nokia's SBTS 18A dictionary has it"
                                 + (" and this release's files set it" if shown else "")
                                 + ". Production's thresholds.", "official")
            if not shown:
                s.notes.append(f"No file of {s.release or 'this release'} shows where the B1 measurement goes: it is on "
                               f"{label(dpr)}, where Nokia's SBTS 18A dictionary has carrierFreqNrCell and the B1 "
                               f"thresholds ({TEMPLATE_RELEASE} puts them in an ENDCDMEASCONF under it instead). Check "
                               "the release takes them there.")
    focus = dn
    if x2 == AUTO:
        auto = s.written("LNBTS", AUTO_X2)
        for k, v in auto:
            s.set(dn, k, v, "Automatic X2 setup: the eNB learns NR cells from UE measurements and sets up X2 to their "
                            "gNB itself, as on the 11 production eNBs with EN-DC.")
        if auto:
            s.notes.append("Automatic X2 setup finds the gNB through the core: the MME must pass the X2 address "
                           "requests on, and the gNB must answer them.")
        else:
            s.todo.append(f"Set up X2 to the gNB: no file of {s.release or 'this release'} has actEndcAutoX2Setup, so "
                          "plan the link instead (an LNADJGNB, the Add a neighbour gNB action).")
    elif x2 != KEEP:
        nb = _endc_gnb(ctx, {"source": x2, "cells": []})
        adj = _AdjPlan(ctx, doc, enb, nb)
        focus = adj.adj()
        s.notes += adj.notes
        for cls, n in adj.made.items():
            s.made[cls] = s.made.get(cls, 0) + n
        problem, note = anr_budget(site, enb, adj.made)
        if problem:
            raise PlanError([problem])
        if note:
            s.notes.append(note)
    s.guessed_note()
    return enb, s, focus if focus != dn else f"{dn}::p::actLteNrDualConnectivity"


def _bts_address(site: Site, gnb: dict) -> tuple[Optional[list[tuple[str, str]]], str]:
    """Where X2 goes on a gNB whose planes name no address: the SRAN eNB's
    C-plane address, else the BTS's only address."""
    for enb in lte_enbs(site):
        for t in site.child(enb["dn"], "TRSNW"):
            for r in (t.get("lists") or {}).get("cPlane", []):
                for k in ("ipV4AddressDN1", "ipV6AddressDN1"):
                    if r.get(k):
                        return [(k, r[k])], f"the address the eNB's C-plane uses ({label(r[k])})"
    found = [(k, m["dn"]) for cls, k in (("IPADDRESSV4", "ipV4AddressDN1"), ("IPADDRESSV6", "ipV6AddressDN1"))
             for m in site.of(cls)]
    if len(found) == 1:
        return [found[0]], f"the BTS's only address ({label(found[0][1])})"
    what = "none" if not found else f"{len(found)}, none of them on a plane yet"
    raise PlanError([f"{label(gnb['dn'])} names no IP address on any plane, and the file has {what}: add its "
                     "transport first (Transport: IP interface, then its NG planes), so X2 goes on the gNB's own "
                     "address."])


def _plan_5g(ctx: Context, doc: Doc, inputs: dict) -> tuple[dict, _Side, str]:
    site = ctx.site
    gnb = next((m for m in _gnbs(site) if m["dn"] == inputs.get("gnb")), None)
    if not gnb:
        raise PlanError(["Pick this file's gNB."])
    s = _Side(ctx, doc, gnb, GNB_RELEASE)
    dn = gnb["dn"]
    lists = gnb.get("lists") or {}
    focus = dn
    if any(not lists.get(plane) for plane in X2_PLANES):
        src = next((r for plane in OTHER_PLANES + X2_PLANES for r in lists.get(plane, [])
                    if r.get("ipV4AddressDN1") or r.get("ipV6AddressDN1")), None)
        if src:
            row = [(k, v) for k, v in src.items() if k in ("ipV4AddressDN1", "ipV6AddressDN1") and v]
            where = f"the address the gNB's other planes use ({label(row[0][1])}), as on every gNB with one in the " \
                    "files this was built from"
        else:
            row, where = _bts_address(site, gnb)
        for plane in X2_PLANES:
            if not lists.get(plane):
                doc.add_item(dn, plane, row, why("endc", f"The X2 {'C' if plane == 'x2Cplane' else 'U'}-plane, on "
                                                         f"{where}.", "files"))
                focus = f"{dn}::list::{plane}"
    s.ready += [plane for plane in X2_PLANES if lists.get(plane)]
    plmns = site.child(dn, "NRPLMN")
    for cell in site.child(dn, "NRCELL"):
        nsa, sa = site.child(cell["dn"], "NRPLMNSET_NSA"), site.child(cell["dn"], "NRPLMNSET_SA")
        if nsa:
            s.ready.append(f"{label(cell['dn'])} NRPLMNSET_NSA")
            continue
        if sa:
            served = (sa[0].get("simple") or {}).get("nrPlmnDNList") or []
            whose = "the same as its SA set, as on all 130 production cells"
        elif plmns:
            served = [m["dn"] for m in sorted(plmns, key=lambda m: natural(m["dn"]))]
            whose = (f"the gNB's {'PLMN' if len(plmns) == 1 else f'{len(plmns)} PLMNs'}: the cell has no PLMN set, "
                     "and production cells list the gNB's PLMN in both")
        elif gnb["p"].get("mcc"):
            s.ready.append(f"{label(cell['dn'])} PLMN (the gNB's own mcc {gnb['p']['mcc']}, mnc {gnb['p'].get('mnc')})")
            continue
        else:
            raise PlanError([f"{label(dn)} has no PLMN (no NRPLMN, no mcc on the NRBTS): add it first (Core network: "
                             "PLMN), then set up EN-DC."])
        params = s.written("NRPLMNSET_NSA", [("cellReservedForOperatorUse",
                                              (sa[0]["p"].get("cellReservedForOperatorUse") if sa else None)
                                              or "notReserved"),
                                             ("configuredEpsTac", "0")], {"cellReservedForOperatorUse"})
        m = s.create(cell["dn"], "NRPLMNSET_NSA", 1, params,
                     f"The PLMNs {label(cell['dn'])} serves EN-DC UEs: {whose}. Production's values.")
        if served:
            doc.set_values(m, "nrPlmnDNList", served, why("endc", f"The PLMNs: {whose}.", "files"))
    qcis = {v for m in site.of("NRDRB_QCI", dn) for v in (m.get("simple") or {}).get("qciValueList", [])}
    missing = [q for q in QCIS if str(q) not in qcis]
    if not s.shown("NRDRB_QCI") and missing:
        s.guessed.add("NRDRB_QCI")
    for q in missing:
        # Production's bearer and profiles for the QCI, through the QoS action.
        out = qos._plan_nr(ctx, doc, qos.NSA, gnb, {"value": str(q), "template": f"builtin|qci|{q}"})
        s.notes += [n for n in out["notes"] if n not in s.notes]
        s.made["NRDRB_QCI"] = s.made.get("NRDRB_QCI", 0) + 1
    if missing:
        s.notes.append(f"QCI {', '.join(map(str, missing))} {'is' if len(missing) == 1 else 'are'} mapped to NR "
                       "bearers as production gNBs map them (NRDRB_QCI to NRDRB-QCI, with production's profiles), so "
                       "the eNB can split those bearers.")
    else:
        s.ready.append("QCI 6-9 bearers")
    s.guessed_note()
    return gnb, s, focus, x2_address(site, gnb)


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    doc = Doc(ctx.raw)
    side = inputs.get("side")
    if side == "4g":
        node, s, focus = _plan_4g(ctx, doc, inputs)
        confirm = ["The BTS has the LTE4088 licence (LTE-NR Dual Connectivity Option 3X).",
                   "The gNB is set up for EN-DC (its 5G side) and accepts X2 from this eNB"
                   + (f" ({lte_cplane(ctx.site, node['dn'], None)})" if lte_cplane(ctx.site, node["dn"], None) else "")
                   + ", on SCTP port 36422."]
    elif side == "5g":
        node, s, focus, address = _plan_5g(ctx, doc, inputs)
        confirm = ["The eNB is set up for EN-DC (its 4G side) and reaches this gNB's X2 address"
                   + (f" ({address})" if address else "") + ", on SCTP port 36422."]
    else:
        raise PlanError(["Pick the side to set up."])
    notes = ([f"Already in place: {', '.join(s.ready)}."] if s.ready else []) + s.notes + [OTHER[side]]
    n, todo = len(doc.changes), s.todo
    what = [f"{n} change{'s' if n != 1 else ''} from the EN-DC template"] if n else []
    what += [f"{len(todo)} to do by hand"] if todo else []
    return finish(ctx, doc, {
        "label": f"EN-DC {side.upper()} side on {label(node['dn'])}",
        "summary": f"{'eNB' if side == '4g' else 'gNB'} {instance(node['dn'])}: "
                   + (", ".join(what) if what else "nothing missing"),
        "notes": notes,
        "todo": todo,
        "confirm": confirm,
        "focus": focus,
    })
