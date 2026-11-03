"""
Set up EN-DC (LTE-NR dual connectivity, NSA option 3X) on one side of the
link: the 4G side (the LTE eNB, the master node) or the 5G side (the gNB,
the secondary node). Each side is checked against a template and gets only
what it lacks, so the review (shown as manual steps first) is the list of
what is missing, to load or to enter by hand in the WebUI.

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
    rule), with production's values where it doesn't.
  - NRDCDPR-0: dlPathlossChg, tPeriodicPhr and tProhibitPhr (every NRDCDPR
    in the tool), plus what this release's files write on it.
  - NRMEASDPR-0 with one nrQuantityConfig (19 of 21), and per NR carrier an
    ENDCDMEASCONF under NRDCDPR: the B1 measurement that triggers EN-DC
    (all 11 production eNBs; xL25R2 moved it there from NRDCDPR). The
    carrier is the SSB's NR-ARFCN, band and subcarrier spacing, from a gNB
    in this file or the tool (sites.ssb_arfcn) or typed in. Its SMTC
    (ssbPeriodicity sf20-r15, ssbDuration sf2, ssbOffset 0) is production's
    and must match the gNB's SSB burst.
  - X2 to the gNB: automatic (actEndcAutoX2Setup and actUeBasedAnrNr true,
    as the 11 production eNBs: the eNB learns NR cells from UEs and sets X2
    up itself), or a planned LNADJGNB (as the lab, endc_gnb), or left as it
    is.
  Every template parameter goes through the release filter: it is written
  only where some file of the eNB's release writes it on that class; a
  class no file of the release has isn't created. The template's own
  release (xL25R2) is exempt: the template is that release's evidence,
  whether or not its files are loaded. What can't be written is left as
  a to-do (`todo`), shown with the manual steps.

5G side (gNB):
  - X2-C and X2-U planes (NRBTS x2Cplane, x2Uplane): 79 of 86 gNBs have
    them, every one on the address its other planes use.
  - Per cell, an NRPLMNSET_NSA beside its NRPLMNSET_SA, with the same
    PLMNs (all 130 production cells). A cell with no PLMN set at all (the
    lab's) is left alone: adding the NSA one only could change what it
    serves.
  - QCI 6-9 bearers (NRDRB_QCI): production maps QCI 5-9 to NRDRB-5..9,
    DRB profiles of their own. Their absence is noted, not filled in: the
    profiles are more than a template value.
"""
from __future__ import annotations

from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, instance, label, release_of, why
from .endc_gnb import _Plan as _AdjPlan
from .endc_gnb import _gnb as _endc_gnb
from .endc_gnb import _sources as _gnb_sources
from .links import Site
from .neighbours import anr_budget, lte_enbs, number
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
        for e in gnb_found:
            if e["ip"] and not any((m["p"].get("cPlaneIpAddr") or "").lower() == e["ip"].lower() for m in adj):
                x2.append({"value": e["key"], "key": e["key"], "group": "Planned link to a gNB in the tool",
                           "label": f"gNB {e['id']}" + (f" {e['name']}" if e.get("name") else "") + f" · {e['ip']}",
                           "details": [f"An LNADJGNB to it, from {e['file']}. Its cell relations: the EN-DC gNB "
                                       "action, or UE-based ANR."]})
        x2s[dn] = x2
        x2_default[dn] = KEEP if (adj or auto) else None
    gnb_opts = [{"value": g["dn"], "key": g["dn"], "label": f"{label(g['dn'])} · gNB {instance(g['dn'])}"
                 + (f" · {g['p'].get('btsName')}" if g["p"].get("btsName") else "")} for g in gnbs]
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
        ],
    }


class _Side:
    """Template checks for one side: what is in place, and changes for the rest."""

    def __init__(self, ctx: Context, doc: Doc, node: dict):
        self.ctx, self.doc, self.site, self.node = ctx, doc, ctx.site, node
        self.release = release_of(node["version"])
        self.index = ctx.release_index()
        self.ready: list[str] = []
        self.notes: list[str] = []
        self.todo: list[str] = []  # needed, but not something the plan can write
        self.made: dict[str, int] = {}

    def knows(self, cls: str) -> bool:
        return not self.index or self.release == TEMPLATE_RELEASE or cls in self.index.get(self.release, {})

    def written(self, cls: str, params: list[tuple[str, str]], core: set[str] = frozenset()) -> list[tuple[str, str]]:
        """The template parameters this release's files write on the class
        (all of them in the template's own release)."""
        if not self.index or self.release == TEMPLATE_RELEASE:
            return params
        names = self.index.get(self.release, {}).get(cls, set())
        return [(k, v) for k, v in params if k in names or k in core]

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
        if not rows:
            s.todo.append(f"Make QCI {x} EN-DC-eligible (qciTab{x} lteNrDualConnectSupport EN-DC, nrPdcpProfIdx "
                          f"{PDCP_PROFILE}): the file has no qciTab{x} to change.")
            continue
        row = rows[0]
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
    elif s.knows("NRMEASDPR"):
        m = s.create(dn, "NRMEASDPR", 0, s.written("NRMEASDPR", NRMEASDPR),
                     "NR measurement defaults for the B1 measurement, as on 19 of the 21 EN-DC eNBs this was built from.")
        doc.add_item(m, "nrQuantityConfig", NR_QUANTITY, why("endc", "The filtering the B1 measurement uses.", "files"))
        quantity = dict(NR_QUANTITY)["quantityConfigId"]
    if carrier:
        ssb, band, scs = carrier
        if ssb in _measured(site, enb):
            s.ready.append(f"B1 measurement of NR-ARFCN {ssb}")
        elif s.knows("ENDCDMEASCONF"):
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
        elif "carrierFreqNrCell" in s.index.get(s.release, {}).get("NRDCDPR", set()):
            s.set(dpr, "carrierFreqNrCell", ssb, f"The NR carrier to measure (B1), NR-ARFCN {ssb}.", "official")
        else:
            s.todo.append(f"Add the B1 measurement of NR-ARFCN {ssb} (band n{band}, {scs} SSB): none of the files "
                          f"loaded for {s.release or 'this release'} shows where it goes. In {TEMPLATE_RELEASE} it is "
                          "an ENDCDMEASCONF under the NRDCDPR (carrierFreqNrCell, ssbSubcarrierSpacing, the B1 "
                          "thresholds and freqBandIndicatorNrL); the SBTS 18A dictionary has the same parameters on "
                          "NRDCDPR.")
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
                          "plan the link instead (an LNADJGNB, the EN-DC gNB action).")
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
    return enb, s, focus if focus != dn else f"{dn}::p::actLteNrDualConnectivity"


def _plan_5g(ctx: Context, doc: Doc, inputs: dict) -> tuple[dict, _Side, str]:
    site = ctx.site
    gnb = next((m for m in _gnbs(site) if m["dn"] == inputs.get("gnb")), None)
    if not gnb:
        raise PlanError(["Pick this file's gNB."])
    s = _Side(ctx, doc, gnb)
    dn = gnb["dn"]
    lists = gnb.get("lists") or {}
    src = next((r for plane in OTHER_PLANES + X2_PLANES for r in lists.get(plane, [])
                if r.get("ipV4AddressDN1") or r.get("ipV6AddressDN1")), None)
    focus = dn
    for plane in X2_PLANES:
        if lists.get(plane):
            s.ready.append(plane)
        elif src:
            row = [(k, v) for k, v in src.items() if k in ("ipV4AddressDN1", "ipV6AddressDN1") and v]
            doc.add_item(dn, plane, row, why("endc", f"The X2 {'C' if plane == 'x2Cplane' else 'U'}-plane on the "
                                                     f"address the gNB's other planes use ({label(row[0][1])}), as on "
                                                     "every gNB with one in the files this was built from.", "files"))
            focus = f"{dn}::list::{plane}"
        else:
            s.todo.append(f"Add {plane}: no other plane of the gNB names an address to put it on.")
    no_sets = 0
    for cell in site.child(dn, "NRCELL"):
        nsa, sa = site.child(cell["dn"], "NRPLMNSET_NSA"), site.child(cell["dn"], "NRPLMNSET_SA")
        if nsa:
            s.ready.append(f"{label(cell['dn'])} NRPLMNSET_NSA")
            continue
        if not sa:
            no_sets += 1
            continue
        plmns = (sa[0].get("simple") or {}).get("nrPlmnDNList") or []
        params = s.written("NRPLMNSET_NSA", [("cellReservedForOperatorUse",
                                              sa[0]["p"].get("cellReservedForOperatorUse") or "notReserved"),
                                             ("configuredEpsTac", "0")], {"cellReservedForOperatorUse"})
        m = s.create(cell["dn"], "NRPLMNSET_NSA", 1, params,
                     f"The PLMNs {label(cell['dn'])} serves EN-DC UEs: the same as its SA set, as on all 130 "
                     "production cells.")
        if plmns:
            doc.set_values(m, "nrPlmnDNList", plmns, why("endc", "The SA set's PLMNs.", "files"))
    if no_sets:
        s.notes.append(f"{no_sets} cell{'s have' if no_sets > 1 else ' has'} no PLMN set (NRPLMNSET_SA or _NSA), so "
                       "none is added: production cells have both, and adding the NSA one alone could change what "
                       "the cell serves.")
    qcis = {v for m in site.of("NRDRB_QCI", dn) for v in (m.get("simple") or {}).get("qciValueList", [])}
    missing = [str(q) for q in QCIS if str(q) not in qcis]
    if missing:
        s.todo.append(f"Map QCI {', '.join(missing)} to NR bearers (NRDRB_QCI, each naming an NRDRB): without them EN-DC "
                      f"bearers of {'that QCI' if len(missing) == 1 else 'those QCIs'} can't be set up on this gNB. "
                      "Production gNBs map QCI 5-9 to DRB profiles of their own, NRDRB-5 to NRDRB-9.")
    else:
        s.ready.append("QCI 6-9 bearers")
    return gnb, s, focus, x2_address(site, gnb)


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    doc = Doc(ctx.raw)
    side = inputs.get("side")
    if side == "4g":
        node, s, focus = _plan_4g(ctx, doc, inputs)
        other = "Run it on the gNB's file too, 5G side."
        confirm = ["The BTS has the LTE4088 licence (LTE-NR Dual Connectivity Option 3X).",
                   "The gNB is set up for EN-DC (its 5G side) and accepts X2 from this eNB"
                   + (f" ({lte_cplane(ctx.site, node['dn'], None)})" if lte_cplane(ctx.site, node["dn"], None) else "")
                   + ", on SCTP port 36422."]
    elif side == "5g":
        node, s, focus, address = _plan_5g(ctx, doc, inputs)
        other = "Run it on the eNB's file too, 4G side."
        confirm = ["The eNB is set up for EN-DC (its 4G side) and reaches this gNB's X2 address"
                   + (f" ({address})" if address else "") + ", on SCTP port 36422."]
    else:
        raise PlanError(["Pick the side to set up."])
    notes = ([f"Already in place: {', '.join(s.ready)}."] if s.ready else []) + s.notes + [other]
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
