"""
Deterministic fallback explanation generator.

Used whenever a parameter name is not present in the curated knowledge base
(backend/app/data/parameters.json). It never returns nothing -- every node in
the tree must produce *some* explanation when double-clicked, even if that
explanation is a clearly-labelled best-effort guess built from the parameter
name, the managed-object class(es) it was seen under, and example values
pulled from real commissioning files.

This is intentionally simple and transparent rather than clever: it expands
known Nokia/3GPP RAN abbreviations token-by-token and composes a sentence.
Anything produced here is tagged confidence="heuristic" so the UI can show a
clear "auto-generated, not verified" badge.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Abbreviation dictionary. Keys are lowercase tokens as they appear after
# camelCase splitting. This is intentionally large -- it is the backbone of
# every heuristic explanation.
# ---------------------------------------------------------------------------
ABBREVIATIONS = {
    "act": "activate/enable", "adm": "administrative", "admin": "administrative",
    "alm": "alarm", "al": "alarm", "ant": "antenna", "auth": "authentication",
    "avg": "average", "bler": "block error rate", "ca": "carrier aggregation",
    "cfg": "configuration", "conf": "configuration", "cid": "cell identity",
    "cell": "cell", "csi": "channel state information", "dl": "downlink",
    "drx": "discontinuous reception", "earfcn": "E-UTRA absolute radio frequency channel number",
    "nrarfcn": "NR absolute radio frequency channel number", "arfcn": "absolute radio frequency channel number",
    "enb": "eNodeB", "gnb": "gNB", "freq": "frequency", "frq": "frequency",
    "ho": "handover", "ims": "IP Multimedia Subsystem (VoLTE)", "idx": "index",
    "ind": "indicator", "mcc": "mobile country code", "mnc": "mobile network code",
    "meas": "measurement", "mimo": "multiple-input multiple-output", "nbr": "neighbor",
    "adj": "adjacent/neighbor", "rel": "relation", "pci": "Physical Cell Identity",
    "plmn": "Public Land Mobile Network", "prb": "Physical Resource Block",
    "pucch": "Physical Uplink Control Channel", "pusch": "Physical Uplink Shared Channel",
    "pdcch": "Physical Downlink Control Channel", "pdsch": "Physical Downlink Shared Channel",
    "pbch": "Physical Broadcast Channel", "qci": "QoS Class Identifier",
    "5qi": "5G QoS Identifier", "rach": "Random Access Channel", "rlc": "Radio Link Control",
    "rrc": "Radio Resource Control", "rsrp": "Reference Signal Received Power",
    "rsrq": "Reference Signal Received Quality", "rssi": "Received Signal Strength Indicator",
    "sinr": "Signal-to-Interference-plus-Noise Ratio", "sctp": "Stream Control Transmission Protocol",
    "ssb": "Synchronization Signal Block", "tac": "Tracking Area Code",
    "thr": "threshold", "thrsh": "threshold", "thrshld": "threshold", "thd": "threshold",
    "timr": "timer", "tmr": "timer", "tx": "transmit", "rx": "receive", "ul": "uplink",
    "vlan": "Virtual LAN", "x2": "X2 interface (inter-eNodeB)", "s1": "S1 interface (eNodeB-to-core)",
    "ng": "NG interface (gNB-to-5G-core)", "xn": "Xn interface (inter-gNB)",
    "f1": "F1 interface (CU-DU)", "eea": "EPS Encryption Algorithm", "eia": "EPS Integrity Algorithm",
    "nea": "5G Encryption Algorithm", "nia": "5G Integrity Algorithm",
    "amf": "Access and Mobility Management Function", "smf": "Session Management Function",
    "upf": "User Plane Function", "mme": "Mobility Management Entity",
    "sgw": "Serving Gateway", "pgw": "PDN Gateway", "drb": "Data Radio Bearer",
    "srb": "Signalling Radio Bearer", "qam": "Quadrature Amplitude Modulation (modulation order)",
    "cqi": "Channel Quality Indicator", "srs": "Sounding Reference Signal",
    "csfb": "Circuit-Switched Fallback", "volte": "Voice over LTE",
    "endc": "E-UTRA-NR Dual Connectivity", "nsa": "Non-Standalone 5G", "sa": "Standalone 5G",
    "dscp": "DiffServ Code Point", "ntp": "Network Time Protocol",
    "ptp": "Precision Time Protocol", "synce": "Synchronous Ethernet",
    "bbmod": "baseband module", "rmod": "radio module", "smod": "system module",
    "ethlk": "Ethernet link", "ipno": "IP network interface", "iprt": "IP route",
    "ipsec": "IPsec", "prd": "period", "dur": "duration", "len": "length",
    "pwr": "power", "offs": "offset", "ofst": "offset", "sec": "seconds",
    "min": "minute(s)/minimum (context-dependent)", "max": "maximum", "num": "number of",
    "cnt": "count", "pct": "percentage", "gw": "gateway", "addr": "address",
    "ip": "IP", "vs": "versus", "cw": "carrier/codeword (context-dependent)",
    "ue": "User Equipment (mobile device)", "bts": "Base Transceiver Station",
    "mrbts": "the whole BTS/gNB site", "lncel": "LTE cell", "lnbts": "LTE BTS",
    "nrcell": "NR (5G) cell", "pm": "performance measurement/monitoring",
    "kpi": "Key Performance Indicator", "hw": "hardware", "sw": "software",
    "fw": "firmware", "temp": "temperature", "volt": "voltage", "curr": "current",
    "cal": "calibration", "diag": "diagnostic", "def": "default", "prio": "priority",
    "lvl": "level", "src": "source", "dst": "destination", "cap": "capability/capacity",
    "sel": "selection", "res": "resource", "rej": "reject", "acc": "access/accept",
    "req": "request", "rsp": "response", "est": "establishment", "rel2": "release",
    "conn": "connection", "disc": "disconnect", "sync": "synchronization",
    "asym": "asymmetric", "sym": "symmetric", "redund": "redundancy", "bw": "bandwidth",
    "chan": "channel", "grp": "group", "tbl": "table", "profl": "profile",
    "profile": "profile", "trs": "Transport", "eqm": "equipment management",
    "vswr": "Voltage Standing Wave Ratio (antenna feeder health)", "ret": "Remote Electrical Tilt",
    "tma": "Tower Mounted Amplifier", "anr": "Automatic Neighbor Relation",
    "ca2": "carrier aggregation", "scell": "secondary cell", "pcell": "primary cell",
    "rat": "Radio Access Technology", "eutran": "E-UTRAN (LTE radio network)",
    "utran": "UTRAN (3G radio network)", "geran": "GERAN (2G radio network)",
    "csg": "Closed Subscriber Group", "barring": "access barring",
    "cac": "Call Admission Control", "aal": "Alarm", "oos": "out of service",
    "is": "in service", "reset": "reset", "boot": "boot/startup",
}

_UNIT_PATTERNS = [
    (re.compile(r"^-?\d+(\.\d+)?\s*dbm$", re.I), "dBm"),
    (re.compile(r"^-?\d+(\.\d+)?\s*db$", re.I), "dB"),
    (re.compile(r"^\d+(\.\d+)?\s*ms$", re.I), "ms"),
    (re.compile(r"^\d+(\.\d+)?\s*sec(onds)?$", re.I), "sec"),
    (re.compile(r"^\d+(\.\d+)?\s*min$", re.I), "min"),
    (re.compile(r"^\d+(\.\d+)?\s*khz$", re.I), "kHz"),
    (re.compile(r"^\d+(\.\d+)?\s*mhz$", re.I), "MHz"),
    (re.compile(r"^\d+(\.\d+)?\s*kb(it)?/?s?$", re.I), "kbit/s"),
    (re.compile(r"^\d+(\.\d+)?\s*mb(it)?/?s?$", re.I), "Mbit/s"),
    (re.compile(r"^\d+(\.\d+)?\s*kb$", re.I), "kB"),
    (re.compile(r"^\d+(\.\d+)?\s*%$"), "%"),
    (re.compile(r"^\d+(\.\d+)?\s*m$", re.I), "m"),
]

_BOOL_VALUES = {"true", "false"}


def _split_camel(name: str) -> list[str]:
    # Insert boundaries: lower->Upper, letter->digit, digit->letter, and
    # sequences of caps followed by a lowercase (e.g. "IPAddr" -> "IP","Addr")
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    s = re.sub(r"([a-zA-Z])([0-9])", r"\1 \2", s)
    s = re.sub(r"([0-9])([a-zA-Z])", r"\1 \2", s)
    s = s.replace("_", " ")
    return [t for t in s.split(" ") if t]


def _expand_token(tok: str) -> str:
    low = tok.lower()
    if low in ABBREVIATIONS:
        return ABBREVIATIONS[low]
    return tok


def _infer_unit(example_values: Iterable[str]) -> Optional[str]:
    for v in example_values:
        v = (v or "").strip()
        for pattern, unit in _UNIT_PATTERNS:
            if pattern.match(v):
                return unit
    return None


def _infer_data_type(example_values: Iterable[str]) -> str:
    vals = [(v or "").strip().lower() for v in example_values if v is not None]
    if not vals:
        return "string"
    if all(v in _BOOL_VALUES for v in vals):
        return "boolean"
    if all(re.match(r"^-?\d+$", v) for v in vals):
        return "integer"
    if all(re.match(r"^-?\d+(\.\d+)?$", v) for v in vals):
        return "decimal"
    if all(re.match(r"^-?\d+(\.\d+)?\s*[a-zA-Z%/]+$", v) for v in vals):
        return "integer" if all(re.match(r"^-?\d+\s", v + " ") for v in vals) else "decimal"
    return "enum" if len(set(vals)) <= max(1, len(vals) - 1) and len(vals) > 1 else "string"


def generate(name: str, classes: Optional[Iterable[str]] = None,
             example_values: Optional[Iterable[str]] = None) -> dict:
    """Build a best-effort explanation for a parameter name we have no curated
    entry for. Always returns a usable dict -- never raises, never empty."""
    classes = list(classes or [])
    example_values = [v for v in (example_values or []) if v]

    tokens = _split_camel(name)
    expanded = [_expand_token(t) for t in tokens]
    phrase = " ".join(expanded).strip()
    if not phrase:
        phrase = name

    lead = tokens[0].lower() if tokens else ""
    class_ctx = f" on the {classes[0]} object" if classes else ""

    if lead in ("act", "en", "enable", "is", "allow") or (example_values and set(v.lower() for v in example_values) <= _BOOL_VALUES):
        sentence = (
            f"Likely a true/false switch that enables or disables a behavior related to "
            f"\"{phrase}\"{class_ctx}."
        )
    elif lead in ("max",):
        sentence = f"Likely sets the maximum allowed value for \"{' '.join(expanded[1:]) or phrase}\"{class_ctx}."
    elif lead in ("min",):
        sentence = f"Likely sets the minimum allowed value for \"{' '.join(expanded[1:]) or phrase}\"{class_ctx}."
    elif lead in ("num", "n", "cnt"):
        sentence = f"Likely a count/number of \"{' '.join(expanded[1:]) or phrase}\"{class_ctx}."
    elif "threshold" in phrase.lower() or lead in ("thr", "thrsh", "thd"):
        sentence = f"Likely a threshold value used to trigger or gate behavior related to \"{phrase}\"{class_ctx}."
    elif "timer" in phrase.lower() or lead in ("t", "timr", "tmr"):
        sentence = f"Likely a timer/duration setting related to \"{phrase}\"{class_ctx}."
    else:
        sentence = f"Nokia RAN configuration parameter related to \"{phrase}\"{class_ctx}."

    sentence += (
        " This description was auto-generated from the parameter's name and usage context "
        "(not individually verified against Nokia's official parameter dictionary), because "
        "this parameter did not appear frequently enough in the sample files to be hand-researched."
    )

    return {
        "description": sentence,
        "confidence": "heuristic",
        "dataType": _infer_data_type(example_values),
        "unit": _infer_unit(example_values),
        "notes": None,
    }
