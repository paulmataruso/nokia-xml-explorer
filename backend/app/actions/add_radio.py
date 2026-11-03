"""
Add a radio: a new RMOD copied from a radio of this file, or from one of a
kind this file lacks in another file, cabled to free ports of a baseband
card.

A radio is more than its RMOD (PROJECT_STATE §9.9, "Hardware actions"):
- its antennas (ANTL, or PHYANT on a massive-MIMO radio) and RSL, which
  come along;
- one CABLINK per optical cable, under HWTOP, from a baseband port
  (firstEndpointLabel OPT or SFP, firstEndpointPortId) to the radio's own
  port, with the link protocol, speed and IQ compression of the template's
  cables. A port is never cabled twice (137 of 137 files);
- where the card lists an SFP per cabled port (hwPortId RF{port}), one for
  each new port;
- where SYNC.targetDNList is used, the radio in it (it lists every RMOD in
  every file that uses it).

Not copied: moduleLocation and antennaLabel, which name the template's
place. The feeder loss and delays (ANTL totalLoss, antennaPathDelayDL/UL)
are the template's, with a note. From another file, values pass the
release filter: written only where some file of this file's release sets
them on that class.

Free ports: the ports cards of the same kind have cables on in the files,
minus the ones cabled here. Refused: an RMOD id the file uses, a port that
is cabled already or not offered, more ports than the template has cables.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from . import Context, PlanError, finish
from ..ca import _load
from .doc import Doc, instance, label, natural, parent_dn, release_of, why
from .hardware import PLACE_PARAMS, base, cables, corpus_view, modules, used_ports
from .links import Site
from .product_code import _name

ID = "add-radio"
TITLE = "Add a radio"
GROUP = "Hardware"
SUMMARY = "A new radio module like one of the site's or another file's, cabled to free baseband ports."
UI = "form"
KEYWORDS = "hardware RMOD radio module CABLINK cable port optical SFP SYNC ANTL PHYANT"

KIDS = ("ANTL", "PHYANT", "RSL")
FEEDER = ("totalLoss", "antennaPathDelayDL", "antennaPathDelayUL", "ulDelay")


def _fzm(site: Site) -> bool:
    return any("_FZM_" in (m["version"] or "") for m in site.of("RMOD") + site.of("SMOD"))


def _shape_key(r: dict) -> str:
    return f"{r['code']}|{r['antl']}|{r['phyant']}|{r['cables']}"


def _donors(ctx: Context) -> list[dict]:
    """Radios of codes this file lacks, from the other files: one per code
    and shape (antennas, cables), the one with the values most files share.
    Same platform (AirScale or Flexi Zone) only."""
    here = {base(m["p"].get("prodCodePlanned")) for m in ctx.site.of("RMOD")}
    fzm = _fzm(ctx.site)
    # Where the site cables its radios, a radio from a partial export without cables isn't one to copy.
    cabled = any(cables(ctx.site, m["dn"]) for m in ctx.site.of("RMOD")) or not ctx.site.of("RMOD")
    by_shape: dict[str, Counter] = {}
    first: dict[tuple[str, str], tuple[dict, dict]] = {}
    for f in ctx.corpus():
        if (f["source"], f["name"]) == (ctx.source, ctx.filename):
            continue
        seen = set()
        for r in (f.get("hardware") or {}).get("radios", []):
            if r["code"] in here or r["fzm"] != fzm or (r["code"], r["sig"]) in seen or (cabled and not r["cables"]):
                continue
            seen.add((r["code"], r["sig"]))
            by_shape.setdefault(_shape_key(r), Counter())[r["sig"]] += 1
            first.setdefault((_shape_key(r), r["sig"]), (f, r))
    out = []
    for shape, sigs in sorted(by_shape.items(), key=lambda kv: (kv[0].split("|")[0], -sum(kv[1].values()))):
        sig, n = sigs.most_common(1)[0]
        f, r = first[(shape, sig)]
        out.append({**r, "file": f, "files": sum(sigs.values()), "same": n})
    return out


def _card_ports(ctx: Context) -> dict[str, set[tuple[str, str]]]:
    """Ports cards of each code have cables on, in any file."""
    out: dict[str, set] = {}
    for f in ctx.corpus():
        for b in (f.get("hardware") or {}).get("basebands", []):
            out.setdefault(b["code"], set()).update(tuple(p) for p in b["ports"])
    return out


def _free_ports(ctx: Context, card: dict, known: dict) -> tuple[list[tuple[str, str]], bool]:
    """A card's free ports, and whether they come from the files (False:
    no file shows the kind's ports, so the two after the highest used)."""
    used = used_ports(ctx.site, card["dn"])
    ports = known.get(base(card["p"].get("prodCodePlanned")), set()) | used
    if len(ports) > len(used):
        return sorted(ports - used, key=lambda p: (p[0], natural(p[1]))), True
    labels = Counter(lab for lab, _ in used) or Counter({"OPT": 1})
    lab = labels.most_common(1)[0][0]
    top = max([int(i) for _, i in used if i.isdigit()] or [0])
    return [(lab, str(top + 1)), (lab, str(top + 2))], False


def _describe(ctx: Context):
    products = ctx.kb.get("products") or {}
    view = corpus_view(ctx.corpus())
    return lambda code: _name(base(code), products, view)


def _shape(antl: int, phyant: int, n: int, protocols: list[str]) -> str:
    bits = [f"{phyant} PHYANT" if phyant else f"{antl} ANTL",
            f"{n} cable{'s' if n != 1 else ''}" + (f" ({', '.join(protocols)})" if protocols else "")]
    return " · ".join(bits)


def _spread(d: dict) -> str:
    rel = f" ({release_of(d['version'])})" if d["version"] else ""
    if d["files"] == 1:
        return f"In one file{rel}."
    if d["same"] == d["files"]:
        return f"In {d['files']} files, all set alike{rel}."
    if d["same"] == 1:
        return f"In {d['files']} files, each set differently; this copies one{rel}."
    return f"In {d['files']} files; this copies the settings {d['same']} of them use{rel}."


def available(ctx: Context) -> Optional[str]:
    if ctx.site.of("RMOD"):
        return None
    if ctx.site.of("BBMOD") and _donors(ctx):
        return None
    return "This file has no radio to copy, and no baseband card to cable one from another file to."


def setup(ctx: Context) -> dict:
    site = ctx.site
    describe = _describe(ctx)
    known = _card_ports(ctx)
    cards = site.of("BBMOD")
    mods = {m["dn"]: m for m in modules(site)}
    templates, card_by, card_default, ports_by, ports_default = [], {}, {}, {}, {}

    def card_options(key: str, n: int, prefer: Optional[str]):
        if not n or not cards:
            return
        opts = []
        for card in cards:
            free, from_files = _free_ports(ctx, card, known)
            code = base(card["p"].get("prodCodePlanned"))
            name = describe(code) if code else None
            opts.append({"value": card["dn"], "key": f"{key}|{card['dn']}",
                         "label": f"{label(card['dn'])} · {code or 'no code'}" + (f" {name}" if name else "")
                                  + f" · {len(free)} free port{'s' if len(free) != 1 else ''}",
                         "details": [f"Cabled now: {', '.join(f'{a} {b}' for a, b in sorted(used_ports(site, card['dn']), key=lambda p: (p[0], natural(p[1])))) or 'nothing'}."]})
            ports_by[f"{key}|{card['dn']}"] = [
                {"value": f"{a}|{b}", "label": f"{a} {b}",
                 "hint": None if from_files else "No file shows this card's ports: check it has this one."}
                for a, b in free]
            ports_default[f"{key}|{card['dn']}"] = [f"{a}|{b}" for a, b in free[:n]]
        card_by[key] = opts
        fits = [o["value"] for o in opts if len(ports_by[o["key"]]) >= n]
        card_default[key] = prefer if prefer in fits else (fits or [opts[0]["value"]])[0]

    for rmod in site.of("RMOD"):
        mod = mods[rmod["dn"]]
        name = describe(mod["code"]) if mod["code"] else None
        mine = cables(site, rmod["dn"])
        templates.append({"value": rmod["dn"], "key": rmod["dn"], "group": "This file",
                          "label": f"Like {label(rmod['dn'])} · {mod['code'] or 'no code'}" + (f" {name}" if name else "")
                                   + f" · {_shape(mod['antl'], mod['phyant'], len(mine), mod['protocols'])}",
                          "details": [f"Carries {', '.join(mod['cells'])}." if mod["cells"] else "Carries no cell."]})
        card = next((c["p"]["firstEndpointDN"] for c in mine if "/BBMOD-" in (c["p"].get("firstEndpointDN") or "")), None)
        card_options(rmod["dn"], len(mine), card)
    if cards:
        for d in _donors(ctx):
            key = f"file|{_shape_key(d)}"
            name = describe(d["code"])
            templates.append({"value": f"file|{d['file']['key']}|{d['dn']}", "key": key, "group": "Kinds from other files",
                              "label": f"A {d['code']}" + (f" {name}" if name else "")
                                       + f" · {_shape(d['antl'], d['phyant'], d['cables'], d['protocols'])}",
                              "details": [_spread(d)]})
            card_options(key, d["cables"], None)
    taken = {int(instance(m["dn"])) for m in site.of("RMOD") if instance(m["dn"]).isdigit()}
    free_id = next(i for i in range(1, 10_000) if i not in taken)
    return {
        "intro": "A new radio module with its antennas, cabled to free ports of a baseband card. It carries no cell "
                 "until one is put on it (Add a 5G cell, Add an LTE cell).",
        "fields": [
            {"id": "template", "label": "Copy", "type": "select", "options": templates,
             "default": next((t["value"] for t in templates if t["group"] == "This file"), None)},
            {"id": "rmod", "label": "RMOD id", "type": "text", "default": str(free_id),
             "hint": "Not one the site uses."},
            {"id": "card", "label": "Cable it to", "type": "select", "dependsOn": "template", "optionsByKey": card_by,
             "defaultByKey": card_default},
            {"id": "ports", "label": "Ports", "type": "checks", "dependsOn": "card", "optionsByKey": ports_by,
             "defaultByKey": ports_default},
        ],
    }


def _template(ctx: Context, value: str) -> tuple[Site, dict, str]:
    """(the site it is in, the RMOD, where it is from)."""
    if value.startswith("file|"):
        _, key, dn = value.split("|", 2)
        f = next((f for f in ctx.corpus() if f["key"] == key), None)
        if not f or not ctx.read:
            raise PlanError(["That file isn't loaded any more: pick the radio again."])
        site = Site(_load(ctx.read(f["name"], f["source"])))
        if dn not in site.by_dn:
            raise PlanError(["That file changed: pick the radio again."])
        return site, site.by_dn[dn], "another file"
    if value not in ctx.site.by_dn or ctx.site.by_dn[value]["cls"] != "RMOD":
        raise PlanError(["Pick the radio to copy."])
    return ctx.site, ctx.site.by_dn[value], "this file"


def plan(ctx: Context, inputs: dict) -> tuple[bytes, dict]:
    site = ctx.site
    problems: list[str] = []
    src_site, rmod, where = _template(ctx, inputs.get("template") or "")
    donor = src_site is not site
    rid = (inputs.get("rmod") or "").strip()
    if not rid.isdigit():
        problems.append("The RMOD id is a number.")
    apeqm = parent_dn(rmod["dn"]) if not donor else (site.of("APEQM") or [{"dn": None}])[0]["dn"]
    if not apeqm:
        problems.append("This file has no APEQM to put a radio under.")
    new_dn = f"{apeqm}/RMOD-{rid}"
    if rid.isdigit() and apeqm and any(instance(m["dn"]) == rid for m in site.of("RMOD")):
        problems.append(f"RMOD-{rid} exists already.")
    template_cables = cables(src_site, rmod["dn"])
    card = inputs.get("card")
    picked = [tuple(p.split("|", 1)) for p in inputs.get("ports") or [] if "|" in p]
    if template_cables:
        if not card or card not in site.by_dn or site.by_dn[card]["cls"] != "BBMOD":
            problems.append("Pick the baseband card to cable the radio to.")
        else:
            free, _ = _free_ports(ctx, site.by_dn[card], _card_ports(ctx))
            bad = [f"{a} {b}" for a, b in picked if (a, b) not in free]
            if bad:
                problems.append(f"{', '.join(bad)} on {label(card)} is cabled already or not one of its ports.")
            if not picked:
                problems.append("Pick a port for each cable.")
            if len(picked) > len(template_cables):
                problems.append(f"The radio has {len(template_cables)} cable{'s' if len(template_cables) != 1 else ''}"
                                f" in the template; pick at most that many ports.")
    if problems:
        raise PlanError(problems)

    doc = Doc(ctx.raw)
    notes, confirm = [], []
    code = base(rmod["p"].get("prodCodePlanned"))
    like = f"a {code or 'radio'} set like one in another file" if donor else f"like {label(rmod['dn'])}"
    whose = "the other file's radio's" if donor else f"{label(rmod['dn'])}'s"
    w = why("add-radio", f"A new radio, {like}" + (f" ({code})" if code and not donor else "") + ".", "donor")
    dropped: list[str] = []
    index = ctx.release_index() if donor else {}
    rel = release_of(next((m["version"] for m in site.of("RMOD") + site.of("APEQM") if m["version"]), None))

    def keep(cls: str, name: str) -> bool:
        """The release filter, for values from another file."""
        ok = not index or rel not in index or name in index[rel].get(cls, set())
        if not ok:
            dropped.append(f"{cls}.{name}")
        return ok

    if donor:
        params = [(k, v) for k, v in rmod["p"].items() if k not in PLACE_PARAMS["RMOD"] and keep("RMOD", k)]
        version = None if site.of("RMOD") else rmod["version"]
        doc.create(apeqm, "RMOD", rid, params, version=version, w=w)
        for name, rows in rmod["lists"].items():
            if keep("RMOD", name):
                for row in rows:
                    doc.add_item(new_dn, name, list(row.items()), w)
        for kid in sorted(src_site.kids.get(rmod["dn"], []), key=lambda k: natural(k["dn"])):
            if kid["cls"] not in KIDS:
                continue
            doc.create(new_dn, kid["cls"], instance(kid["dn"]),
                       [(k, v) for k, v in kid["p"].items() if k not in PLACE_PARAMS.get(kid["cls"], ())
                        and keep(kid["cls"], k)],
                       version=None if site.of(kid["cls"]) else kid["version"], w=w)
    else:
        over = {"": {k: None for k in PLACE_PARAMS["RMOD"]}}
        for kid in site.kids.get(rmod["dn"], []):
            if kid["cls"] == "ANTL":
                over[label(kid["dn"])] = {k: None for k in PLACE_PARAMS["ANTL"]}
        skip = frozenset(k["cls"] for k in site.kids.get(rmod["dn"], []) if k["cls"] not in KIDS)
        doc.clone(rmod["dn"], new_dn, w, overrides=over, skip=skip)
    if any(k["cls"] == "ANTL" and any(f in k["p"] for f in FEEDER) for k in src_site.kids.get(rmod["dn"], [])):
        notes.append(f"The antennas' feeder loss and delays ({', '.join(FEEDER[:3])}) are {whose}: set the new "
                     "radio's feeders'.")

    if template_cables:
        hwtop = parent_dn(template_cables[0]["dn"]) if not donor else (site.of("HWTOP") or [{"dn": None}])[0]["dn"]
        if not hwtop:
            raise PlanError(["This file has no HWTOP to put the radio's cables under."])
        wc = why("add-radio", f"The cable from {label(card)} to the new radio, set like {whose}.", "donor")
        made = []
        for (lab, port), c in zip(picked, template_cables):
            mine = c["p"]
            params = []
            for k, v in mine.items():
                if k == "firstEndpointDN":
                    v = card
                elif k == "firstEndpointLabel":
                    v = lab
                elif k == "firstEndpointPortId":
                    v = port
                elif k == "secondEndpointDN":
                    v = new_dn
                elif not keep("CABLINK", k):
                    continue
                params.append((k, v))
            doc.create(hwtop, "CABLINK", doc.next_free(hwtop, "CABLINK"), params, w=wc)
            made.append(f"{lab} {port}")
        if len(picked) < len(template_cables):
            notes.append(f"{label(rmod['dn'])} has {len(template_cables)} cables; the new radio gets {len(picked)}.")
        confirm.append(f"Cable the radio to {label(card)} {' and '.join(made)}, the ports the plan names.")
        _sfps(doc, site, card, picked, w)
    if dropped:
        notes.append(f"Left out, as no file of this release sets them: {', '.join(sorted(set(dropped))[:8])}"
                     + (" and more" if len(set(dropped)) > 8 else "") + ".")
    for sync in site.of("SYNC"):
        if sync["simple"].get("targetDNList"):
            doc.add_value(sync["dn"], "targetDNList", new_dn,
                          why("add-radio", "SYNC.targetDNList lists every radio of the site, so the new one gets "
                                           "its synchronisation.", "files"))
    notes.append("No cell uses the radio yet: Add a 5G cell or Add an LTE cell puts one on it.")
    return finish(ctx, doc, {"label": f"Add RMOD-{rid}", "summary": f"RMOD-{rid}, {like}.",
                             "notes": notes, "confirm": confirm, "focus": new_dn})


def _sfps(doc: Doc, site: Site, card: str, picked: list[tuple[str, str]], w: dict) -> None:
    """An SFP per new port, where the card has one per cabled port (hwPortId
    "RF3" for OPT 3, "S_RF1" for SFP 1)."""
    sfps = site.child(card, "SFP")
    if not sfps:
        return
    prefixes = {}
    for lab, port in used_ports(site, card):
        for s in sfps:
            hw = s["p"].get("hwPortId") or ""
            if hw.endswith(port) and not hw[: -len(port)][-1:].isdigit():
                prefixes[lab] = hw[: -len(port)]
    for lab, port in picked:
        if lab not in prefixes:
            continue
        hw = prefixes[lab] + port
        if any(s["p"].get("hwPortId") == hw for s in sfps):
            continue
        inst = port if not doc.exists(f"{card}/SFP-{port}") else doc.next_free(card, "SFP")
        doc.create(card, "SFP", inst, [("hwPortId", hw)],
                   w=why("add-radio", f"{label(card)} has an SFP for each cabled port ({prefixes[lab]}n for {lab} n).",
                         "files"))
