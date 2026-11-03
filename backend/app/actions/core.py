"""
Add an MME or AMF, or change the IP address of one: the core node an eNB
(LNMME, S1) or a gNB (SERVEDAMF, NG) connects to.

Only what a configured file carries is written. 189 configured LNMMEs
hold administrativeState, ipAddrPrim, mmeRatSupport and transportNwId, and
117 configured SERVEDAMFs hold administrativeState, amfIPAddress,
amfIPAddressTTL and defaultAMF. The rest (mmeName, relMmeCap, ipAddrSec,
accMmePlmnsList, s1LinkStatus; amfName, relativeAMFCapacity, guAMI,
ngLinkStatus, localCuIpAddr) is learned from the core at link setup. The
SBTS18A dictionary marks the LNMME ones "Value set by the system", and
they appear only in exports from running BTSs. A changed IP drops them,
because they describe the old node.

Checks: the address itself (the ipAddrPrim ranges); the same IP twice on
one transport network (ipAddrPrim's uniqueness note); for an MME, a TRSNW
with that transportNwId where the eNB has TRSNWs (the mme-transport link
rule). Notes say when the BTS has no C-plane address to connect from (a gNB
without ngCplane uses its other planes' address, as 18 SA gNBs do), and
when no subnet or static route in the file reaches the new address. A file
with no transport objects (most Flexi Zone commissioning files) gets
neither: there is nothing to judge by.

A new AMF copies an existing AMF of the gNB (its PLMN and slice support,
NRPLMN_SUPPORT) when there is one, minus what the core reported.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, label, release_of, why
from .transport import (NR_PLANES, check_ip, has_transport, lte_cplane, nr_cplane, plane_refs, reachable,
                        subnets)

ID = "core"
TITLE = "Add or change an MME or AMF"
GROUP = "Core network"
SUMMARY = "Point an eNB at a new MME, or a gNB at a new AMF, or change the address of an existing one."
UI = "form"
KEYWORDS = "MME AMF S1 NG core EPC 5GC LNMME SERVEDAMF ipAddrPrim amfIPAddress IP address"

MME_LEARNED = ("ipAddrSec", "mmeName", "relMmeCap", "s1LinkStatus")
MME_LEARNED_LISTS = ("accMmePlmnsList",)
AMF_LEARNED = ("amfName", "localCuIpAddr", "ngLinkStatus", "relativeAMFCapacity")
AMF_LEARNED_LISTS = ("guAMI",)

LNMME_CLASS = "NOKLTE:LNMME"
SERVEDAMF_CLASS = "com.nokia.srbts.nrbts:SERVEDAMF"

NEW = "new:"  # target values for a new node: "new:<parent distName>"


def _enbs(ctx: Context) -> list[str]:
    return [m["dn"] for m in ctx.site.of("LNBTS")]


def _gnbs(ctx: Context) -> list[str]:
    """gNBs whose release has SERVEDAMF somewhere in the corpus (23R1 NSA
    gNBs have none), or that already have one."""
    index = ctx.release_index()
    out = []
    for m in ctx.site.of("NRBTS"):
        if ctx.site.child(m["dn"], "SERVEDAMF") or not index or \
                "SERVEDAMF" in index.get(release_of(m["version"]), {}):
            out.append(m["dn"])
    return out


def available(ctx: Context) -> Optional[str]:
    if _enbs(ctx) or _gnbs(ctx):
        return None
    if ctx.site.of("NRBTS"):
        return "This file's gNB release has no AMF objects (SERVEDAMF) in any file, and it has no LTE eNB."
    return "This file has no LTE eNB (LNBTS) or NR gNB (NRBTS)."


def _ip_of(m: dict) -> Optional[str]:
    return m["p"].get("ipAddrPrim") if m["cls"] == "LNMME" else m["p"].get("amfIPAddress")


def _transport_ids(ctx: Context, enb: str) -> list[str]:
    return [t["p"].get("transportNwId", "0") for t in ctx.site.child(enb, "TRSNW")]


def setup(ctx: Context) -> dict:
    targets, ips, nets = [], {}, {}
    for enb in _enbs(ctx):
        mmes = ctx.site.child(enb, "LNMME")
        for m in mmes:
            ip = _ip_of(m)
            targets.append({"value": m["dn"], "label": f"{label(m['dn'])} · {ip or 'no address'}",
                            "group": f"MMEs of {label(enb)}", "key": m["dn"],
                            "details": [f"Transport network {m['p'].get('transportNwId', '0')}."]
                            + ([f"Name reported by the MME: {m['p']['mmeName']}."] if m["p"].get("mmeName") else [])})
            ips[m["dn"]] = ip or ""
        key = NEW + enb
        targets.append({"value": key, "label": f"New MME on {label(enb)}", "group": f"MMEs of {label(enb)}",
                        "key": key, "details": [f"{label(enb)} has {len(mmes)} MME{'s' if len(mmes) != 1 else ''}."]})
        ids = _transport_ids(ctx, enb)
        if len(ids) > 1:
            opts = [{"value": i, "label": f"Transport network {i}"} for i in ids]
            nets[key] = opts
            for m in mmes:
                nets[m["dn"]] = opts
    for gnb in _gnbs(ctx):
        amfs = ctx.site.child(gnb, "SERVEDAMF")
        for m in amfs:
            targets.append({"value": m["dn"], "label": f"{label(m['dn'])} · {_ip_of(m) or 'no address'}",
                            "group": f"AMFs of {label(gnb)}", "key": m["dn"],
                            "details": [f"Name reported by the AMF: {m['p']['amfName']}."] if m["p"].get("amfName")
                            else []})
            ips[m["dn"]] = _ip_of(m) or ""
        key = NEW + gnb
        targets.append({"value": key, "label": f"New AMF on {label(gnb)}", "group": f"AMFs of {label(gnb)}",
                        "key": key, "details": [f"{label(gnb)} has {len(amfs)} AMF{'s' if len(amfs) != 1 else ''}."]})
    return {
        "intro": "Sets the address the eNB reaches its MME on (S1), or the gNB its AMF (NG). The name, capacity and "
                 "PLMNs come from the core when the link comes up, so only the address is asked for.",
        "fields": [
            {"id": "target", "label": "MME or AMF", "type": "select", "options": targets},
            {"id": "ip", "label": "IP address", "type": "text", "dependsOn": "target", "defaultByKey": ips,
             "placeholder": "10.0.1.175"},
            {"id": "transportNw", "label": "Transport network", "type": "select", "dependsOn": "target",
             "optionsByKey": nets},
        ],
    }


class _Plan:
    def __init__(self, ctx: Context, doc: Doc):
        self.ctx, self.doc = ctx, doc
        self.index = ctx.release_index()
        self.notes: list[str] = []
        self.problems: list[str] = []
        self.source: Optional[str] = None  # the BTS address the core sees

    def known(self, cls: str, release: Optional[str], name: str) -> bool:
        return not self.index or name in self.index.get(release, {}).get(cls, set())

    def forget_learned(self, dn: str, names, lists, node: str) -> None:
        doc = self.doc
        for name in names:
            if doc.get(dn, name) is not None:
                doc.unset(dn, name, why("core", f"Reported by the old {node}; the BTS learns it again from the new "
                                                "one when the link comes up.", "official", (name, None)))
        for name in lists:
            for i in reversed(range(len(doc.items(dn, name)))):
                doc.remove_item(dn, name, i, why("core", f"Reported by the old {node}; learned again from the new "
                                                         "one.", "official", (name, None)))

    def no_source(self, bts: str, where: str, refs: list[str]) -> None:
        """Note that the BTS has no address to reach the core from: either
        its planes point at an address object the file lacks, or there is no
        plane at all. A file with no transport has nothing to judge by."""
        if refs:
            self.notes.append(f"{label(bts)}'s C-plane points at {refs[0]}, which isn't in this file, so it "
                              "has no address to reach the core from. The site check reports it too.")
        elif has_transport(self.ctx.site):
            self.notes.append(f"{label(bts)} has no C-plane address ({where}), so it has no address to reach "
                              "the core from.")

    def reach(self, ip: str, node: str) -> None:
        how = reachable(self.ctx.site, ip)
        version = ipaddress.ip_address(ip).version
        if how is None and not any(net.version == version for _, net in subnets(self.ctx.site)):
            self.notes.append(f"The BTS has no IPv{version} address in this file, so it can't reach {ip}. "
                              f"Use an IPv{6 if version == 4 else 4} address for the {node} peer, or add IPv{version} "
                              "transport.")
        elif how is None:
            self.notes.append(f"Nothing in this file reaches {ip}: it is on none of the BTS's subnets, no static "
                              f"route covers it, and there is no default route. Add a route before loading, or "
                              f"the {node} link won't come up.")

    def mme(self, target: str, ip: str, transport: Optional[str]) -> str:
        doc, site = self.doc, self.ctx.site
        if target.startswith(NEW):
            enb, existing = target[len(NEW):], None
        else:
            existing = site.by_dn[target]
            enb = target.rsplit("/", 1)[0]
        siblings = [m for m in site.child(enb, "LNMME") if m["dn"] != target]
        ids = _transport_ids(self.ctx, enb)
        nw = transport or (existing["p"].get("transportNwId") if existing else None) \
            or (siblings[0]["p"].get("transportNwId") if siblings else None) or (ids[0] if ids else "0")
        if ids and nw not in ids:
            self.problems.append(f"{label(enb)} has no TRSNW with transportNwId {nw} (it has {', '.join(ids)}).")
        for m in siblings:
            if _ip_of(m) == ip and m["p"].get("transportNwId", "0") == nw:
                self.problems.append(f"{label(m['dn'])} already uses {ip} on transport network {nw}; Nokia requires "
                                     "each MME address to be unique per transport network.")
        if self.problems:
            return ""
        cplane = lte_cplane(site, enb, nw if ids else None)
        self.source = cplane
        if not cplane:
            refs = [r for t in site.child(enb, "TRSNW") if t["p"].get("transportNwId", "0") == nw
                    for r in plane_refs(site, t["dn"], ("cPlane",))]
            self.no_source(enb, "TRSNW cPlane or IPNO cPlaneIpAddress", refs)
        self.reach(ip, "S1")
        rel = release_of(site.by_dn[enb]["version"])
        if existing:
            doc.set(target, "ipAddrPrim", ip, why("core", "The MME's new address.", "choice"))
            if transport and existing["p"].get("transportNwId") != transport:
                doc.set(target, "transportNwId", transport, why("core", "Reached over this transport network.",
                                                                "choice"))
            self.forget_learned(target, MME_LEARNED, MME_LEARNED_LISTS, "MME")
            return f"{target}::p::ipAddrPrim"
        rat = siblings[0]["p"].get("mmeRatSupport") if siblings else None
        params = [("administrativeState", "unlocked"), ("ipAddrPrim", ip),
                  ("mmeRatSupport", rat or "Wideband-LTE"), ("transportNwId", nw)]
        params = [(k, v) for k, v in params if k in ("ipAddrPrim",) or self.known("LNMME", rel, k)]
        taken = [m["dn"] for m in site.child(enb, "LNMME")]
        inst = doc.next_free(enb, "LNMME", 0).rsplit("-", 1)[-1]
        dn = doc.create(enb, "LNMME", inst, params, full_class=None if taken else LNMME_CLASS,
                        version=None if taken else site.by_dn[enb]["version"],
                        w=why("core", f"A new MME at {ip}" + (f"; the eNB connects from {cplane}" if cplane else "")
                              + ". Unlocked, so the eNB sets up S1 to it when loaded.", "choice"))
        return f"{dn}::p::ipAddrPrim"

    def amf(self, target: str, ip: str) -> str:
        doc, site = self.doc, self.ctx.site
        if target.startswith(NEW):
            gnb, existing = target[len(NEW):], None
        else:
            existing = site.by_dn[target]
            gnb = target.rsplit("/", 1)[0]
        siblings = [m for m in site.child(gnb, "SERVEDAMF") if m["dn"] != target]
        for m in siblings:
            if _ip_of(m) == ip:
                self.problems.append(f"{label(m['dn'])} already uses {ip}.")
        if self.problems:
            return ""
        cplane = nr_cplane(site, gnb)
        self.source = cplane
        if not cplane:
            self.no_source(gnb, "NRBTS ngCplane, or another plane's address", plane_refs(site, gnb, NR_PLANES))
        self.reach(ip, "NG")
        if existing:
            doc.set(target, "amfIPAddress", ip, why("core", "The AMF's new address.", "choice"))
            self.forget_learned(target, AMF_LEARNED, AMF_LEARNED_LISTS, "AMF")
            return f"{target}::p::amfIPAddress"
        inst = doc.next_free(gnb, "SERVEDAMF", 1).rsplit("-", 1)[-1]
        dst = f"{gnb}/SERVEDAMF-{inst}"
        reason = f"A new AMF at {ip}" + (f"; the gNB connects from {cplane}" if cplane else "") + \
            ". Unlocked, so the gNB sets up NG to it."
        if siblings:
            src = siblings[0]["dn"]
            doc.clone(src, dst, why("core", reason + " The same PLMN and slice support as the gNB's other AMF.",
                                    "choice"),
                      overrides={"": {"amfIPAddress": ip, "administrativeState": "Unlocked",
                                      **{k: None for k in AMF_LEARNED}}})
            for name in AMF_LEARNED_LISTS:
                for i in reversed(range(len(doc.items(dst, name)))):
                    doc.remove_item(dst, name, i, why("core", f"Reported by {label(src)}'s AMF; the new one reports "
                                                              "its own.", "official", (name, None)))
            if site.child(src, "NRPLMN_SUPPORT"):
                self.notes.append(f"The new AMF supports the same PLMNs and slices as {label(src)} (NRPLMN_SUPPORT). "
                                  "Change them if this AMF serves others.")
        else:
            doc.create(gnb, "SERVEDAMF", inst,
                       [("administrativeState", "Unlocked"), ("amfIPAddress", ip), ("amfIPAddressTTL", "5"),
                        ("defaultAMF", "true")],
                       full_class=SERVEDAMF_CLASS, version=site.by_dn[gnb]["version"],
                       w=why("core", reason + " amfIPAddressTTL 5 and defaultAMF true as on every production gNB.",
                             "files"))
        return f"{dst}::p::amfIPAddress"


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    target = inputs.get("target") or ""
    ip = (inputs.get("ip") or "").strip()
    parent = target[len(NEW):] if target.startswith(NEW) else target.rsplit("/", 1)[0]
    lte = parent in _enbs(ctx) and (target.startswith(NEW) or ctx.site.by_dn.get(target, {}).get("cls") == "LNMME")
    nr = parent in _gnbs(ctx) and (target.startswith(NEW) or ctx.site.by_dn.get(target, {}).get("cls") == "SERVEDAMF")
    if not (lte or nr):
        raise PlanError(["Pick an MME or AMF."])
    if not ip:
        raise PlanError(["Enter the IP address."])
    problem, notes = check_ip(ip)
    if problem:
        raise PlanError([problem])
    if not target.startswith(NEW) and _ip_of(ctx.site.by_dn[target]) == ip and not inputs.get("transportNw"):
        raise PlanError([f"{label(target)} already has {ip}."])

    doc = Doc(ctx.raw)
    p = _Plan(ctx, doc)
    p.notes.extend(notes)
    focus = p.mme(target, ip, inputs.get("transportNw") or None) if lte else p.amf(target, ip)
    if p.problems:
        raise PlanError(p.problems)
    node = "MME" if lte else "AMF"
    what = f"new {node} on {label(parent)}" if target.startswith(NEW) else label(target)
    return finish(ctx, doc, {
        "label": f"{node} {ip}: {what}",
        "summary": f"{what} at {ip}",
        "notes": p.notes,
        "confirm": [f"The {node} at {ip} accepts {'S1' if lte else 'NG'} connections from this "
                    f"{'eNB' if lte else 'gNB'}" + (f" ({p.source})" if p.source else "")
                    + ", with its PLMN and TAC configured on the core side."],
        "focus": focus,
    })
