"""
Set the BTS's NTP and DNS servers.

Where they live:
  - TNLSVC (SBTS/AirScale): NTP under MNL/MNLENT/SYNC/CLOCK, with the
    servers in ntpServerIpAddrOrFqdnList (the 25R2 files, 32; addresses
    or host names) or ntpServerIpAddrList (19A-23R1, 6; addresses only),
    and the source address in ntpSourceIpAddressDN; DNS under MNL/MNLENT
    (serverIpAddressPrimary, serverIpAddressSecondary).
  - FTM (Flexi Zone): INTP ntpServers and IDNS serverIpAddress /
    serverIpAddress2 under the FTM's IPNO.
A missing NTP or DNS object is created where the files keep it.

Refused, after the dictionary: a loopback or 0.x NTP server, a repeated
one, servers of two IP versions (NTP ntpServerIpAddrList); a DNS server
in a range the dictionary rules out (DNS serverIpAddressPrimary), a
secondary without a primary. Noted: servers nothing in the file routes
to. The config-source parameters (ntpServerConfigSource,
dnsServerConfigSource) are left as they are: 26 of the 32 newer NTP
objects with servers in the files this was built from don't set one.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Optional

from . import Context, PlanError, finish
from .doc import Doc, label, parent_dn, release_of, why
from .links import Site, _runtime
from .transport import reachable

ID = "ntp-dns"
TITLE = "Set NTP and DNS servers"
GROUP = "Transport"
SUMMARY = "The time servers the BTS syncs to and the name servers it asks, with the NTP source address."
UI = "form"
KEYWORDS = "NTP DNS time server name server INTP IDNS ntpServerIpAddrList ntpServerIpAddrOrFqdnList resolver"

KEEP = "keep"
UNSET = "none"  # not "": the form takes an empty select as unanswered
_FQDN = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}\.?$")
# IPv4 ranges the dictionary rules out for a DNS server (DNS serverIpAddressPrimary).
DNS_BANNED = (("0.0.0.0/8", "0.x"), ("224.0.0.0/4", "multicast"), ("240.0.0.0/4", "class E"),
              ("192.168.253.0/24", "Nokia-internal"), ("192.168.254.0/23", "Nokia-internal"),
              ("127.0.0.0/8", "loopback"))


def _ip(value: Optional[str]):
    try:
        return ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None


def _one(site: Site, cls: str) -> Optional[dict]:
    return next((m for m in site.of(cls) if not _runtime(m["dn"])), None)


def _model(site: Site) -> Optional[str]:
    """FTM where the transport is Flexi Zone's (those files have an MNLENT
    too, but keep NTP and DNS under the FTM), else TNLSVC."""
    if site.of("FTM") and not site.of("TNLSVC"):
        return "FTM"
    if site.of("TNLSVC") or site.of("MNLENT"):
        return "TNLSVC"
    return None


def _ntp_home(site: Site) -> bool:
    """Whether the file has an NTP object, or somewhere to put one."""
    if _model(site) == "FTM":
        return True
    return bool(_one(site, "NTP") or _one(site, "CLOCK"))


def _ntp_list(m: Optional[dict], version: Optional[str]) -> str:
    """The list an NTP object holds its servers in: the one it has, else
    the one its release writes."""
    for name in ("ntpServerIpAddrOrFqdnList", "ntpServerIpAddrList"):
        if m and name in (m.get("simple") or {}):
            return name
    year = re.search(r"(\d\d)", release_of(version) or "")
    return "ntpServerIpAddrOrFqdnList" if not year or int(year.group(1)) >= 25 else "ntpServerIpAddrList"


def current(site: Site) -> dict:
    """The servers the file sets now."""
    if _model(site) == "FTM":
        intp, idns = _one(site, "INTP"), _one(site, "IDNS")
        return {"ntp": list((intp or {}).get("simple", {}).get("ntpServers", [])), "source": None,
                "dns1": (idns or {}).get("p", {}).get("serverIpAddress") or "",
                "dns2": (idns or {}).get("p", {}).get("serverIpAddress2") or ""}
    ntp, dns = _one(site, "NTP"), _one(site, "DNS")
    lname = _ntp_list(ntp, (ntp or {}).get("version"))
    return {"ntp": list((ntp or {}).get("simple", {}).get(lname, [])),
            "source": (ntp or {}).get("p", {}).get("ntpSourceIpAddressDN"),
            "dns1": (dns or {}).get("p", {}).get("serverIpAddressPrimary") or "",
            "dns2": (dns or {}).get("p", {}).get("serverIpAddressSecondary") or ""}


def _unset(value: str) -> bool:
    ip = _ip(value)
    return not value or (ip is not None and ip.is_unspecified)


def available(ctx: Context) -> Optional[str]:
    site = ctx.site
    model = _model(site)
    if model == "TNLSVC" and (_one(site, "MNLENT") or _one(site, "CLOCK")):
        return None
    if model == "FTM" and _one(site, "IPNO"):
        return None
    return "This file has neither a management entity (MNLENT) nor a Flexi Zone IPNO to hold NTP and DNS settings."


def setup(ctx: Context) -> dict:
    site = ctx.site
    now = current(site)
    fields = [
        {"id": "ntp", "label": "NTP servers", "type": "text", "optional": True,
         "default": ", ".join(now["ntp"]), "placeholder": "Addresses, separated by commas",
         "hint": "Empty leaves the file's NTP servers as they are."
                 + (" Host names work on 25R2 and later." if _model(site) == "TNLSVC" else "")},
    ] if _ntp_home(site) else []
    if _model(site) == "TNLSVC" and _ntp_home(site):
        own = [m for m in site.of("IPADDRESSV4") + site.of("IPADDRESSV6") if not _runtime(m["dn"])]
        options = [{"value": UNSET, "label": "Not set (the BTS picks)"}] + [
            {"value": m["dn"], "label": f"{label(parent_dn(m['dn']))} · {m['p'].get('localIpAddr')}"} for m in own]
        fields.append({"id": "source", "label": "NTP source address", "type": "select", "options": options,
                       "default": now["source"] if now["source"] in {o["value"] for o in options} else UNSET})
    fields += [
        {"id": "dns1", "label": "Primary DNS", "type": "text", "optional": True,
         "default": "" if _unset(now["dns1"]) else now["dns1"], "placeholder": "Not set",
         "hint": "Empty leaves the file's DNS servers as they are."},
        {"id": "dns2", "label": "Secondary DNS", "type": "text", "optional": True,
         "default": "" if _unset(now["dns2"]) else now["dns2"], "placeholder": "Not set",
         "hint": "Asked when the primary doesn't answer."},
    ]
    intro = "Sets the time and name servers. A field left as it is changes nothing."
    if not _ntp_home(site):
        intro += " This file has no CLOCK under SYNC, so it has nowhere to keep NTP servers; only DNS is set here."
    return {"intro": intro, "fields": fields}


def _ntp_problems(servers: list[str], fqdn_ok: bool) -> list[str]:
    out, versions = [], set()
    for s in servers:
        ip = _ip(s)
        if ip is None:
            if not (fqdn_ok and _FQDN.match(s)):
                out.append(f"{s!r} isn't an IP address" + (" or a host name." if fqdn_ok else
                                                          " (this release's NTP list takes addresses only)."))
            continue
        versions.add(ip.version)
        if ip.version == 4 and (ip in ipaddress.ip_network("127.0.0.0/8") or ip in ipaddress.ip_network("0.0.0.0/8")):
            out.append(f"{s} can't be an NTP server: the dictionary rules out loopback and 0.0.0.0-0.255.255.255.")
        elif ip.is_multicast or ip.is_unspecified or ip.is_loopback:
            out.append(f"{s} can't be an NTP server.")
    if len({x.lower() for x in servers}) != len(servers):
        out.append("An NTP server is listed twice; the dictionary wants each once.")
    if len(versions) > 1:
        out.append("The NTP servers mix IPv4 and IPv6; the dictionary wants one IP version for all of them.")
    return out


def _dns_problems(value: str, which: str) -> list[str]:
    ip = _ip(value)
    if ip is None:
        return [f"The {which} DNS {value!r} isn't an IP address."]
    if ip.version == 4:
        if ip == ipaddress.ip_address("255.255.255.255"):
            return [f"{ip} can't be a DNS server (broadcast)."]
        for net, what in DNS_BANNED:
            if ip in ipaddress.ip_network(net):
                return [f"{ip} is in the {what} range {net}, which the dictionary rules out for a DNS server."]
    elif ip.is_unspecified or ip.is_multicast or ip.is_loopback:
        return [f"{ip} can't be a DNS server."]
    return []


def _split(text: str) -> list[str]:
    return [s for s in re.split(r"[\s,;]+", (text or "").strip()) if s]


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    model = _model(site)
    now = current(site)
    problems, notes = [], []
    servers = _split(inputs.get("ntp") or "")
    ntp = _one(site, "NTP") if model == "TNLSVC" else _one(site, "INTP")
    version = (ntp or _one(site, "CLOCK") or _one(site, "MNLENT") or {}).get("version")
    lname = _ntp_list(ntp, version) if model == "TNLSVC" else "ntpServers"
    if servers and servers != now["ntp"]:
        problems += _ntp_problems(servers, lname == "ntpServerIpAddrOrFqdnList")
    dns1, dns2 = (inputs.get("dns1") or "").strip(), (inputs.get("dns2") or "").strip()
    if dns1:
        problems += _dns_problems(dns1, "primary")
    if dns2:
        problems += _dns_problems(dns2, "secondary")
        if not dns1:
            problems.append("A secondary DNS needs a primary one (the dictionary: it can be set only if the primary "
                            "is).")
    if dns1 and dns1 == dns2:
        problems.append("The primary and secondary DNS are the same server.")
    source = inputs.get("source", KEEP) if model == "TNLSVC" else KEEP
    if source not in (KEEP, UNSET) and source not in site.by_dn:
        problems.append("Pick the NTP source address from the list.")
    if problems:
        raise PlanError(problems)

    doc = Doc(ctx.raw)
    w = lambda reason, basis="choice": why("ntp-dns", reason, basis)
    changed = False
    if servers and servers != now["ntp"]:
        if ntp is None:
            if model == "TNLSVC":
                clock = next((m for m in site.of("CLOCK") if not _runtime(m["dn"])), None)
                if clock is None:
                    raise PlanError(["The file has no CLOCK under SYNC to put an NTP object in."])
                dn = doc.create(clock["dn"], "NTP", "1", [], w=w("Holds the NTP servers; the files keep it under "
                                                                  "SYNC's CLOCK."))
            else:
                dn = doc.create(_one(site, "IPNO")["dn"], "INTP", "1", [], w=w("Holds the NTP servers."))
            notes.append(f"The file had no {label(dn).split('-')[0]}; it gets {label(dn)}.")
        else:
            dn = ntp["dn"]
        doc.set_values(dn, lname, servers, w(f"The NTP servers, in the order the BTS tries them"
                                             + ("; this release's list takes addresses or host names."
                                                if lname == "ntpServerIpAddrOrFqdnList" else ".")))
        changed = True
        if ntp is not None and ntp["p"].get("ntpServerConfigSource") not in (None, "Manual"):
            notes.append(f"{label(ntp['dn'])}.ntpServerConfigSource is {ntp['p']['ntpServerConfigSource']}; the "
                         "servers listed here may be ignored unless it is Manual.")
    chosen = None if source == UNSET else source
    if source != KEEP and model == "TNLSVC" and chosen != now["source"]:
        if ntp is None and not changed:
            raise PlanError(["Set the NTP servers too: the file has no NTP object yet."])
        dn = ntp["dn"] if ntp else dn
        if chosen:
            doc.set(dn, "ntpSourceIpAddressDN", source, w("The address the BTS's NTP client sends from."))
        else:
            doc.unset(dn, "ntpSourceIpAddressDN", w("The BTS picks the NTP source address."))
        changed = True

    if model == "TNLSVC":
        dns, f1, f2, cls = _one(site, "DNS"), "serverIpAddressPrimary", "serverIpAddressSecondary", "DNS"
    else:
        dns, f1, f2, cls = _one(site, "IDNS"), "serverIpAddress", "serverIpAddress2", "IDNS"
    old1, old2 = ("" if _unset(now["dns1"]) else now["dns1"]), ("" if _unset(now["dns2"]) else now["dns2"])
    if dns1 and (dns1, dns2) != (old1, old2):
        if dns is None:
            parent = _one(site, "MNLENT") if model == "TNLSVC" else _one(site, "IPNO")
            ddn = doc.create(parent["dn"], cls, "1", [(f1, dns1)] + ([(f2, dns2)] if dns2 else []),
                             w=w("The name servers; the files keep them here."))
            notes.append(f"The file had no {cls}; it gets {label(ddn)}.")
        else:
            ddn = dns["dn"]
            if dns1 != old1:
                doc.set(ddn, f1, dns1, w("The DNS server the BTS asks first."))
            if dns2 and dns2 != old2:
                doc.set(ddn, f2, dns2, w("Asked when the primary doesn't answer."))
            elif not dns2 and old2:
                if model == "FTM":
                    doc.set(ddn, f2, "0.0.0.0", w("No secondary DNS; Flexi Zone files write 0.0.0.0 for none."))
                else:
                    doc.unset(ddn, f2, w("No secondary DNS."))
        changed = True
    if not changed:
        raise PlanError(["Nothing to change: the file already has these servers."])

    unreached = [s for s in servers + [dns1, dns2] if _ip(s) and not reachable(site, s)]
    if unreached:
        notes.append(f"Nothing in the file routes to {', '.join(dict.fromkeys(unreached))}: no subnet or static route "
                     "covers it. Add a route, or the BTS can't reach it.")
    if any(_ip(s) is None for s in servers):
        notes.append("NTP host names need a DNS server the BTS can reach.")
    parts = []
    if servers and servers != now["ntp"]:
        parts.append(f"NTP {', '.join(servers)}")
    if dns1 and (dns1, dns2) != (old1, old2):
        parts.append(f"DNS {dns1}" + (f", {dns2}" if dns2 else ""))
    return finish(ctx, doc, {
        "label": "NTP and DNS",
        "summary": "; ".join(parts) or "The NTP source address",
        "notes": notes,
        "confirm": ["The servers answer the BTS's address: firewalls between them are outside this file."],
        "focus": None,
    })
