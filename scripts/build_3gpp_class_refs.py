#!/usr/bin/env python3
"""
Adds a `threeGpp` field to every entry in backend/app/data/classes.json,
answering "does this managed-object class correspond to something 3GPP
actually standardizes, and if so, which spec?"

This is a SEPARATE, additive step from the main scripts/build_knowledge.py
pipeline (run this AFTER it, and after merge_official_reference.py /
build_class_catalog.py) -- it only ever adds/overwrites the `threeGpp` key,
never touches description/category/confidence/anything else, and is safe
to re-run any time classes.json is regenerated.

Why this exists as a hand-curated mapping rather than an extraction
pipeline: unlike parameters.json's `threeGppRef`/`threeGppName` fields
(populated in merge_official_reference.py straight from a "References"
column Nokia's own official parameter dictionary already has -- see that
script), Nokia's class-level dictionary has NO equivalent "which 3GPP spec
does this managed-object class correspond to" column at all. There is no
extraction to do; this is judgment, grounded in: (a) real 3GPP spec
identities verified via web search on 2026-09-08 (not assumed from
training-data memory -- see the SPECS dict below, every title here was
independently confirmed), and (b) each class's own already-researched
description in classes.json (confidence-tiered, corpus-cross-checked, see
PROJECT_STATE.md §8 for that KB's own methodology).

Ground rule, matching this project's established standard (see the
timeZone cross-class-fallback incident in PROJECT_STATE.md §8.5): NEVER
invent a plausible-looking citation. A huge fraction of Nokia's managed
object classes are pure vendor OAM/hardware modeling that 3GPP simply
does not standardize -- those get an honest "vendor-specific, no 3GPP
reference" status, not a guessed one. Where a DIFFERENT standards body
(3GPP2 for CDMA2000, IEEE for Ethernet/802.1X, ITU-T for PTP/SyncE, IETF
for DNS/NTP/SCTP/routing, WInnForum/FCC for CBRS, the MulteFire Alliance
for MulteFire, AISG for RET/TMA antenna-line control) demonstrably governs
the underlying concept instead, that's noted too -- it's honest and more
useful than a bare "not applicable", but it is explicitly NOT a 3GPP
reference and must never be confused for one in the UI.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "backend" / "app" / "data"

# Every spec cited below was verified via web search on 2026-09-08 against
# real results (3GPP's own archive index pages, or their listed titles) --
# not reproduced from memory alone. See PROJECT_STATE.md for the research
# trail. `series` is just the spec's own leading number, used to build the
# archive URL.
SPECS = {
    "28.622": "Telecommunication management; Generic Network Resource Model (NRM) Integration Reference Point (IRP); Information Service (IS)",
    "28.652": "Telecommunication management; Universal Terrestrial Radio Access Network (UTRAN) Network Resource Model (NRM) Integration Reference Point (IRP); Information Service (IS)",
    "28.658": "Telecommunication management; Evolved Universal Terrestrial Radio Access Network (E-UTRAN) Network Resource Model (NRM) Integration Reference Point (IRP); Information Service (IS)",
    "28.541": "Management and orchestration; 5G Network Resource Model (NRM); Stage 2 and stage 3",
    "36.331": "Evolved Universal Terrestrial Radio Access (E-UTRA); Radio Resource Control (RRC); Protocol specification",
    "38.331": "NR; Radio Resource Control (RRC) protocol specification",
    "25.331": "Universal Terrestrial Radio Access Network (UTRAN); Radio Resource Control (RRC) Protocol Specification",
    "23.203": "Policy and charging control architecture",
    "23.401": "General Packet Radio Service (GPRS) enhancements for Evolved Universal Terrestrial Radio Access Network (E-UTRAN) access",
    "23.501": "System architecture for the 5G System (5GS)",
    "33.401": "3GPP System Architecture Evolution (SAE); Security architecture",
    "33.501": "Security architecture and procedures for 5G system",
    "36.413": "Evolved Universal Terrestrial Radio Access Network (E-UTRAN); S1 Application Protocol (S1AP)",
    "38.413": "NG-RAN; NG Application Protocol (NGAP)",
    "36.423": "Evolved Universal Terrestrial Radio Access Network (E-UTRAN); X2 Application Protocol (X2AP)",
    "38.423": "NG-RAN; Xn Application Protocol (XnAP)",
    "38.473": "NG-RAN; F1 Application Protocol (F1AP)",
    "25.413": "UTRAN Iu interface RANAP signalling",
    "36.211": "Evolved Universal Terrestrial Radio Access (E-UTRA); Physical channels and modulation",
    "38.211": "NR; Physical channels and modulation",
    "36.104": "Evolved Universal Terrestrial Radio Access (E-UTRA); Base Station (BS) radio transmission and reception",
    "32.511": "Telecommunication management; Automatic Neighbour Relation (ANR) management; Concepts and requirements",
    "32.425": "Telecommunication management; Performance Management (PM); Performance measurements Evolved Universal Terrestrial Radio Access Network (E-UTRAN)",
    "28.552": "Management and orchestration; 5G performance measurements",
    "37.340": "NR; Multi-connectivity; Overall description; Stage-2",
    "36.412": "Evolved Universal Terrestrial Radio Access Network (E-UTRAN); S1 signalling transport",
    "38.412": "NG-RAN; NG signalling transport",
}


def _spec(spec: str) -> dict:
    series = spec.split(".")[0]
    return {
        "spec": f"TS {spec}",
        "title": SPECS[spec],
        "url": f"https://www.3gpp.org/ftp/Specs/archive/{series}_series/{spec}/",
    }


def standardized(*spec_numbers: str, note: str | None = None) -> dict:
    return {"status": "standardized", "specs": [_spec(s) for s in spec_numbers], "note": note}


def other_standard(body: str, note: str) -> dict:
    return {"status": "other-standard", "specs": [], "note": f"Standardized by {body}, not 3GPP. {note}"}


def vendor_specific(note: str | None = None) -> dict:
    return {"status": "vendor-specific", "specs": [], "note": note}


# ---------------------------------------------------------------------------
# Per-class overrides. Anything not listed here defaults to vendor_specific()
# with no note -- see DEFAULT_NOTE_BY_CATEGORY below for a slightly more
# informative default note on a few categories where that's honest and safe
# to say in bulk (e.g. "Equipment" classes model physical hardware, which
# 3GPP's Network Resource Model does not describe at this granularity).
# ---------------------------------------------------------------------------
OVERRIDES: dict[str, dict] = {}


# ---- Site root / generic NRM ----
OVERRIDES["MRBTS"] = standardized("28.622", note="Corresponds to the generic NRM's top-level ManagedElement IOC; the granular equipment hierarchy underneath it (cabinets/modules/etc.) is Nokia's own extension beyond what 3GPP's generic model specifies.")
OVERRIDES["MRBTSDESC"] = vendor_specific("Free-text/descriptive metadata about the site -- not part of the 3GPP NRM's attribute set.")

# ---- E-UTRAN (LTE) NRM-level objects ----
for n in ("LNBTS", "LNBTS_FDD", "LNBTS_TDD"):
    OVERRIDES[n] = standardized("28.658", note="Corresponds to the E-UTRAN NRM's ENBFunction IOC.")
for n in ("LNCEL", "LNCEL_FDD", "LNCEL_TDD"):
    OVERRIDES[n] = standardized("28.658", "36.331", note="The class itself corresponds to the E-UTRAN NRM's EUtranCellFDD/TDD IOC (TS 28.658); most of its individual RRC-facing parameters (SIB content, mobility thresholds, PUCCH/PDCCH config, etc.) are themselves specified in TS 36.331.")
OVERRIDES["LNHENB"] = standardized("36.331", note="HeNB (Home eNodeB) detection/handling is a 3GPP-defined mobility feature; the OAM parameters for managing it as a neighbor are Nokia's own, but the underlying concept and RRC signalling are standardized.")

# ---- NR (5G) NRM-level objects ----
OVERRIDES["NRBTS"] = standardized("28.541", note="Aggregates the 5G NRM's GNBCUCPFunction/GNBDUFunction concepts under one site-level object.")
OVERRIDES["NRDU"] = standardized("28.541", note="Corresponds to the 5G NRM's GNBDUFunction IOC.")
OVERRIDES["NRCUUP"] = standardized("28.541", note="Corresponds to the 5G NRM's GNBCUUPFunction IOC.")
for n in ("NRCELL", "NRCELL_FDD"):
    OVERRIDES[n] = standardized("28.541", "38.331", note="The class corresponds to the 5G NRM's NRCellDU/NRCellCU IOCs (TS 28.541); most of its RRC-facing parameters are themselves specified in TS 38.331.")
OVERRIDES["NRCELLGRP"] = standardized("28.541", note="A cell-grouping construct within the 5G NRM's cell hierarchy.")
OVERRIDES["NRBEAMMAP"] = vendor_specific("Beam management procedures themselves are standardized (TS 38.213/38.214), but this specific logical-beam-ID-to-physical-antenna-pattern mapping table is Nokia's own implementation detail, not a 3GPP-defined structure.")

# ---- RRC-level channel/SIB/mobility configuration (LTE) ----
for n in ("APUCCH_FDD", "APUCCH_TDD", "MPUCCH_FDD", "MPUCCH_TDD"):
    OVERRIDES[n] = standardized("36.331", note="Configures the RRC PUCCH-Config information element.")
OVERRIDES["SIB"] = standardized("36.331", note="System Information Blocks and their content are entirely 3GPP-defined broadcast structures.")
OVERRIDES["ACBPR"] = standardized("36.331", note="Access Class Barring is broadcast via SIB2's ac-BarringInfo, a 3GPP-defined RRC structure.")
for n in ("CAGENB", "CAPR", "CAREL"):
    OVERRIDES[n] = standardized("36.331", note="Carrier Aggregation itself, and its RRC-signalled measurement/configuration IEs, are 3GPP-standardized (see also TS 36.300 for the overall CA description); this specific profile/decision object is Nokia's own OAM wrapper around those standardized IEs.")
for n in ("LBPUCCHRDPR", "TMSWPR"):
    OVERRIDES[n] = vendor_specific("Built on top of standardized concepts (PUCCH resource config / transmission mode, TS 36.331 and TS 36.213 respectively), but the load-based decision logic and thresholds in this specific profile are Nokia's own algorithm, not something 3GPP specifies.")
OVERRIDES["MFIRECEL"] = other_standard("the MulteFire Alliance (an independent industry alliance, not part of 3GPP)", "MulteFire re-uses LTE radio technology in unlicensed spectrum without requiring a licensed anchor carrier, but is specified outside 3GPP.")

# ---- RRC-level channel/BWP configuration (NR) ----
for n in ("PDCCH", "PDCCH_CONFIG_COMMON", "PDCCH_CONFIG_DEDICATED"):
    OVERRIDES[n] = standardized("38.331", note="Configures the RRC PDCCH-Config / PDCCH-ConfigCommon information elements.")
OVERRIDES["PDSCH"] = standardized("38.331", note="Configures the RRC PDSCH-Config information element.")
OVERRIDES["BWP_PROFILE"] = standardized("38.331", note="Bandwidth Parts are defined via the RRC BWP-Downlink/BWP-Uplink information elements.")
OVERRIDES["NRSYSINFO_PROFILE"] = standardized("38.331", note="NR System Information Blocks and their content are 3GPP-defined broadcast structures.")
OVERRIDES["NRPLMN"] = standardized("38.331", note="Broadcast PLMN identity is carried in SIB1's PLMN-IdentityInfoList, a 3GPP-defined RRC structure.")

# ---- Mobility / neighbor relations ----
for n in ("LNADJ", "LNADJL", "LNREL"):
    OVERRIDES[n] = standardized("32.511", "36.331", note="LTE-to-LTE neighbor relations are governed by the ANR management spec (TS 32.511) and configured/signalled via TS 36.331's mobility IEs.")
for n in ("LNADJGNB", "LNRELGNBCELL", "LTEENB"):
    OVERRIDES[n] = standardized("37.340", "32.511", note="LTE-NR (EN-DC) neighbor relations are governed by the multi-connectivity spec (TS 37.340), with ANR concepts from TS 32.511 also applying.")
for n in ("LNADJX", "LNRELX", "LNHOX", "XPARAM"):
    OVERRIDES[n] = other_standard("3GPP2 (a separate standards body for CDMA2000, not part of 3GPP)", "CDMA2000 1xRTT/1xEV-DO air-interface parameters are specified in 3GPP2's own C.S00xx document series, entirely outside 3GPP's remit.")
for n in ("IAFIM", "IRFIM", "UFFIM", "LNHOIF", "MODPR", "MOIMP", "MOPR", "REDRT", "MORED", "LTAC", "RIM", "TAC"):
    OVERRIDES[n] = standardized("36.331", note="Idle-mode mobility priorities, handover/redirect targets, and Tracking Area configuration are all broadcast via 3GPP-defined SIB/RRC structures.")
for n in ("NRIAFIM", "NRIRFIM", "NRMEASDPR", "TRACKINGAREA"):
    OVERRIDES[n] = standardized("38.331", note="NR idle-mode mobility and Tracking Area configuration are broadcast via 3GPP-defined SIB/RRC structures.")
for n in ("NRRFSP_PROFILE", "NRSPID_PROFILE"):
    OVERRIDES[n] = standardized("36.413", note="RFSP Index and Subscriber Profile ID (SPID) are standardized Information Elements carried over S1AP (also referenced from the core network side in TS 23.401's Annex on RAT/Frequency Selection Priority).")
OVERRIDES["ANR"] = standardized("32.511", note="This IS the Automatic Neighbor Relation function the spec is named for.")
for n in ("ANRPRL", "ANRPRW"):
    OVERRIDES[n] = standardized("32.511")
for n in ("AMLEPR", "IFGDPR", "IFGPR"):
    OVERRIDES[n] = vendor_specific("Frequency-layer prioritization for idle-mode reselection is broadcast via standardized SIB IEs (TS 36.331), but this specific mobility/load-balancing decision profile and its thresholds are Nokia's own algorithm.")

# ---- Core network interfaces ----
OVERRIDES["LNMME"] = standardized("36.413", note="Represents an S1-MME peer; the S1AP protocol and its IEs are entirely 3GPP-defined.")
for n in ("SNSSAI",):
    OVERRIDES[n] = standardized("23.501", note="S-NSSAI (network slice identity) is defined in the 5G System Architecture spec (also numbered in TS 23.003).")
OVERRIDES["SERVEDAMF"] = standardized("38.413", note="AMF configuration/selection information is carried over NGAP.")
OVERRIDES["NRPLMN_SUPPORT"] = standardized("38.413", note="Per-PLMN NG-RAN support/broadcast is signalled via NGAP and SIB1.")
OVERRIDES["NRSCTP"] = standardized("38.412", note="SCTP is itself an IETF protocol (RFC 4960), but 3GPP specifies its use as the NG-interface signalling transport in this spec.")
OVERRIDES["SCTP"] = standardized("36.412", note="SCTP is itself an IETF protocol (RFC 4960), but 3GPP specifies its use as the S1-interface signalling transport in this spec.")

# ---- QoS ----
OVERRIDES["NRDRB_5QI"] = standardized("23.501", note="The 5QI (5G QoS Identifier) standardized characteristics table is defined in this spec, §5.7.4.")
for n in ("DSCP2PCPMAP", "DSCP2QMAP", "DSCPTOQMAP", "PCP2QMAP", "QOS", "FSTSCH", "IPAPP"):
    OVERRIDES[n] = vendor_specific("Transport-layer QoS marking (DiffServ/DSCP is IETF RFC 2474; 802.1p/PCP is IEEE 802.1Q) -- 3GPP doesn't standardize a vendor's specific DSCP-to-queue mapping table.")
OVERRIDES["TWAMP"] = other_standard("the IETF (RFC 5357)", "Two-Way Active Measurement Protocol is an IETF specification, not a 3GPP one, even though it's commonly used to measure a mobile backhaul's transport performance.")

# ---- Performance measurement (PM) family -- genuinely 3GPP-standardized ----
for n in ("PMQAP", "PMCCP", "PMTNL", "PMTNLINT", "PMRNL", "PMPLM", "PMRPQH", "PMCADM", "PMCADM_R", "PMMNL"):
    OVERRIDES[n] = standardized("32.425", note="3GPP defines a standardized catalog of E-UTRAN performance counters in this spec; this object controls which of Nokia's (standardized-and-proprietary) counters get collected, so applies loosely -- see the note before assuming every counter this config touches has a matching 3GPP counter definition.")
for n in ("NRPMCCP", "NRPMRNL"):
    OVERRIDES[n] = standardized("28.552", note="3GPP defines a standardized catalog of NR/5GC performance measurements in this spec; this object controls which of Nokia's (standardized-and-proprietary) counters get collected.")

# ---- Security: mostly Nokia OAM/PKI, with two genuine 3GPP-mandated exceptions ----
for n in ("IPSECC", "IPSECC_R"):
    OVERRIDES[n] = standardized("33.401", "33.501", note="3GPP mandates IPsec for backhaul/network-domain security (see each spec's Network Domain Security annex); the specific IPsec tunnel/certificate configuration mechanics here are Nokia's own O&M implementation of that requirement, not themselves 3GPP-specified.")
OVERRIDES["NRX2LINK_TRUST"] = standardized("33.501", note="3GPP requires inter-node interfaces to be secured (see the Network Domain Security annex); this specific trusted-peer list mechanism is Nokia's own implementation.")
for n in ("PNASC",):
    OVERRIDES[n] = other_standard("IEEE (802.1X)", "Port-based network access control is an IEEE Ethernet standard, unrelated to 3GPP.")

# ---- Synchronization: PTP/SyncE/GNSS/NTP are ITU-T/IEEE/IETF, not 3GPP ----
for n in ("PTPMASTER", "TOP", "TOPB", "TOPF", "TOPP", "TOPP_R", "ECPRIMASTER"):
    OVERRIDES[n] = other_standard("the ITU-T (G.8271/G.8275 Telecom Profiles) and IEEE (1588 PTP)", "3GPP requires certain synchronization ACCURACY budgets for radio operation (e.g. TS 36.133/38.133), but does not itself define the PTP/eCPRI synchronization protocol used to achieve them.")
OVERRIDES["SYNCE"] = other_standard("the ITU-T (G.8262/G.8264 Synchronous Ethernet)", "Frequency distribution over Ethernet physical layer, unrelated to 3GPP.")
for n in ("NTP", "NTPS", "NTP_R", "INTP"):
    OVERRIDES[n] = other_standard("the IETF (RFC 5905, NTPv4)", "Coarse time sync, unrelated to 3GPP.")

# ---- Transport/networking: IETF/IEEE, not 3GPP ----
for n in ("BFDGRP",):
    OVERRIDES[n] = other_standard("the IETF (RFC 5880, BFD)", "Fast link-failure detection, unrelated to 3GPP.")
for n in ("ETHAPP",):
    OVERRIDES[n] = other_standard("the IEEE (802.1ag) and ITU-T (Y.1731)", "Ethernet Connectivity Fault Management, unrelated to 3GPP.")
for n in ("DNS", "IDNS"):
    OVERRIDES[n] = other_standard("the IETF (RFC 1035 and successors)", "unrelated to 3GPP.")
for n in ("VLANIF", "IVIF"):
    OVERRIDES[n] = other_standard("the IEEE (802.1Q)", "VLAN tagging, unrelated to 3GPP.")
OVERRIDES["POE"] = other_standard("the IEEE (802.3af/at/bt)", "Power-over-Ethernet, unrelated to 3GPP.")

# ---- Antenna-line hardware (RET/TMA): AISG, not 3GPP ----
for n in ("ALD", "ALD_R", "ANTL", "ANTL_R", "RETU", "RETU_R", "CHANNEL", "CHANNELGROUP", "RSL", "RSL_R"):
    OVERRIDES[n] = other_standard("AISG (Antenna Interface Standards Group)", "Remote Electrical Tilt / Tower-Mounted Amplifier control protocol (AISG v2/v3), an industry standard independent of 3GPP.")

# ---- CBRS (US-specific spectrum sharing): WInnForum/FCC, not 3GPP ----
for n in ("CBSDCEL", "NRCBSDCELL", "CBSD", "NRCBSD", "CBRSPR", "NRCBRSPR", "CBSDCERTH", "CBRSCERTH", "CADPRCBRS", "SASUSERGROUP", "NRSASUSERGROUP"):
    OVERRIDES[n] = other_standard("the Wireless Innovation Forum (WInnForum) and US FCC Part 96 rules", "Citizens Broadband Radio Service (band 48, US 3.5 GHz shared spectrum) is a US regulatory/WInnForum framework, not a 3GPP specification (though the radio cell itself, once configured, operates per normal 3GPP band definitions).")

# ---- Timezone: IANA tz database, not a telecom standard at all ----
OVERRIDES["TIME"] = other_standard("the IANA Time Zone Database", "Timezone/DST rules are a general software convention (see the ~543-option tz database), not any telecom standards body's concern.")


def build():
    classes_path = DATA_DIR / "classes.json"
    classes = json.loads(classes_path.read_text())

    default_notes = {
        "Equipment": "Physical hardware modeling (cabinets, modules, cables, transceivers, etc.) at this granularity is Nokia's own equipment model -- 3GPP's Network Resource Model does not standardize individual hardware unit types.",
        "Transport-Networking": "General IP/Ethernet transport configuration -- governed by IETF/IEEE standards where a standard applies at all, not by 3GPP.",
        "Site-Common": "Site-wide Nokia O&M/administrative configuration, not part of any 3GPP-defined model.",
        "Feature-Function-Config": "A Nokia feature-configuration/administration wrapper; some of the underlying radio features it controls are 3GPP-standardized even where this specific object isn't -- check the individual parameters (phase 2 of this work) for those cases.",
        "Other": None,
    }

    changed = 0
    for short, entry in classes.items():
        if short in OVERRIDES:
            entry["threeGpp"] = OVERRIDES[short]
        else:
            note = default_notes.get(entry.get("category"), None)
            entry["threeGpp"] = vendor_specific(note)
        changed += 1

    classes_path.write_text(json.dumps(classes, indent=1, sort_keys=True))

    by_status = {"standardized": 0, "other-standard": 0, "vendor-specific": 0}
    for entry in classes.values():
        by_status[entry["threeGpp"]["status"]] += 1
    print(f"Classes annotated: {changed}")
    print(f"  standardized (real 3GPP spec):  {by_status['standardized']}")
    print(f"  other-standard (non-3GPP body): {by_status['other-standard']}")
    print(f"  vendor-specific (no ref):       {by_status['vendor-specific']}")


if __name__ == "__main__":
    build()
