#!/usr/bin/env python3
"""
Corpus check for the voice action (backend/app/actions/voice.py).

Sweep: every eNB and gNB the form offers, on all its cells, once with every
feature and once with none: no crash; the site check finds no new error or
warning; the dictionary's rules on what the features need hold where the
release has the parameters (actConvVoice: harqMaxTrVoLteDl in every cell;
actTtiBundling: its mandatory settings and actTtibRsc; proactive grants:
both periods; actQci1eVTT: its configuration row); a gNB maps 5QI 1 and 5
afterwards, NRDRB_5QI-1 only for 5QI 1, and a production gNB's QoS is left
as it is; the same again on the result is refused (nothing to change).
Round trip: every eNB with conversational voice on and every gNB with VoNR
cells has its voice settings taken out (switches off, values and rows of
the features each cell runs removed; on an eNB its QCI 1 row too) and is
set up again with the features it ran, on the same cells. Each setting must come back with the value it
had; what doesn't is listed by parameter. It is a failure on cells of the
profiles' own release that ran every feature, which must come back exactly.

Usage: python3 scripts/voice_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.actions import Context, PlanError, qos, voice  # noqa: E402
from app.actions.doc import Doc, label, release_of, why  # noqa: E402
from app.ca import _load  # noqa: E402
from app.actions.links import Site  # noqa: E402
from qos_check import load, production  # noqa: E402

W = why("check", "round trip", "choice")
QOS_CLASSES = {"NRDRB_5QI", "NRDRB", "NRDRB_MAC", "NRDRB_PDCP", "NRDRB_RLC_AM", "NRDRB_RLC_UM"}

LTE_SWITCHES = {"actTtiBundling": "false", "actQci1eVTT": "false", "actQci1BlerTgt": "false",
                "maxNumVoLteProactUlGrantsPerTti": "0", "voLteProactUlGrantPeriodRegTx": "0",
                "voLteProactUlGrantPeriodTtib": "0"}
LTE_VALUES = (["harqMaxTrVoLteDl", "n310Qci1", "t310Qci1", "harqMaxTrUlTtiBundling", "actTtibRsc", "eUlLaLowMcsThr",
               "eUlLaLowPrbThr", "ttibMinUlPrb"]
              + [k for rows in (voice.TTIB, voice.TTIB_SINR, voice.TTIB_DWELL, voice.TTIB_EXTRA, voice.GRANTS)
                 for k, _ in rows])
LTE_ROWS = ("qci1eVTTConfig", "qci1BlerTgtConfig")
NR_SWITCHES = {"actVoNR": "false", "actEnhancedVoNR": "false", "actGBRAdmissionControl": "off",
               "voiceFBMode": "disabled",
               **{k: "false" for k, _, kind in voice.NR_LA + voice.NR_COVERAGE if kind == "switch"}}
NR_VALUES = [k for k, _ in voice.NR_CELL] + [k for k, _, kind in voice.NR_LA + voice.NR_COVERAGE if kind == "value"]
LTE_FULL = {"actTtiBundling": "true", "actQci1eVTT": "true", "actQci1BlerTgt": "true"}
NR_FULL = {"actVoNR": "true", "actEnhancedVoNR": "true", "actTargetBlerVoNR": "true", "actVoNRIncCodingGain": "true",
           "voiceFBMode": "redirection"}


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def rule_problems(raw, index, side, dn):
    """The dictionary's must-configure rules the features bring, where the
    release has the parameter."""
    site = Site(_load(raw))
    out = []

    def has(m, name):
        return m["p"].get(name) is not None or name not in index.get(release_of(m["version"]), {}).get(m["cls"], ())

    if side == voice.LTE:
        enb = site.by_dn[dn]
        conv = any(s["p"].get("actConvVoice") == "true"
                   for s in site.child(dn, "LNBTS_FDD") + site.child(dn, "LNBTS_TDD"))
        for c in site.child(dn, "LNCEL"):
            p = c["p"]
            need = []
            if conv:
                need.append("harqMaxTrVoLteDl")
            if p.get("actTtiBundling") == "true":
                need += ["harqMaxTrUlTtiBundling", "ttiBundlingBlerTarget", "ttiBundlingBlerThreshold",
                         "ttiBundlingSinrThreshold", "ttibOperMode", "actTtibRsc"]
            if (p.get("maxNumVoLteProactUlGrantsPerTti") or "0") != "0":
                need += ["voLteProactUlGrantPeriodRegTx", "voLteProactUlGrantPeriodTtib"]
            out += [f"{label(c['dn'])} lacks {n}" for n in need if not has(c, n)]
            if p.get("actQci1eVTT") == "true" and not c["lists"].get("qci1eVTTConfig"):
                out.append(f"{label(c['dn'])} has actQci1eVTT on and no qci1eVTTConfig")
            if p.get("actQci1eVTT") == "true" and not conv:
                out.append(f"{label(c['dn'])} has actQci1eVTT on without conversational voice")
        del enb
    else:
        mapped = qos._mapped(Doc(raw), dn, qos.SA)
        out += [f"5QI {v} isn't mapped" for v in ("1", "5") if v not in mapped]
    return out


def sweep(corpus, raws, index, counts, failures):
    for (source, name), raw in raws.items():
        ctx = Context(raw, name, source, corpus=lambda: corpus, release_index=lambda: index)
        if voice.available(ctx):
            counts[("unavailable", "")] += 1
            continue
        try:
            fields = {f["id"]: f for f in voice.setup(ctx)["fields"]}
        except Exception:
            failures.append(f"{name}: setup crashed\n{traceback.format_exc()}")
            continue
        prod = production(ctx.mos)
        for t in fields["target"]["options"]:
            side, _, dn = t["value"].partition("|")
            for kind in ("all", "none"):
                inputs = {"target": t["value"]}
                if kind == "none":
                    inputs["features"] = []
                if t["key"] in fields["slices"]["optionsByKey"]:
                    inputs["slices"] = fields["slices"]["defaultByKey"][t["key"]]
                where = f"{name} {label(dn)} {kind}"
                try:
                    out, plan = voice.plan(ctx, inputs)
                except PlanError as e:
                    counts[(f"{side} {kind}", "refused")] += 1
                    if "set up already" not in " ".join(e.problems):
                        failures.append(f"{where}: refused: {e.problems}")
                    continue
                except Exception:
                    failures.append(f"{where}: crashed\n{traceback.format_exc()}")
                    continue
                counts[(f"{side} {kind}", "ok")] += 1
                if new_findings(plan):
                    failures.append(f"{where}: new findings {new_findings(plan)[:3]}")
                if kind == "all":
                    failures += [f"{where}: {p}" for p in rule_problems(out, index, side, dn)]
                after = Doc(out)
                ones = [c["dn"] for c in plan["changes"] if c["op"] == "create" and c["class"] == "NRDRB_5QI"
                        and c["dn"].endswith("-1") and after.values(c["dn"], "fiveqiValueList") != ["1"]]
                if ones:
                    failures.append(f"{where}: made {ones}")
                if side == voice.NR and dn in prod:
                    qos_changes = [label(c["dn"]) for c in plan["changes"] if c.get("class") in QOS_CLASSES]
                    if qos_changes:
                        failures.append(f"{where}: changed a production gNB's QoS: {qos_changes[:4]}")
                try:
                    voice.plan(Context(out, name, source, corpus=lambda: corpus, release_index=lambda: index), inputs)
                    failures.append(f"{where}: repeat not refused")
                except PlanError:
                    pass
                except Exception:
                    failures.append(f"{where}: repeat crashed\n{traceback.format_exc()}")


def _lte_features(p):
    return {f for f, on in (("ttib", p.get("actTtiBundling") == "true"),
                            ("grants", (p.get("maxNumVoLteProactUlGrantsPerTti") or "0") != "0"),
                            ("evtt", p.get("actQci1eVTT") == "true"), ("bler", p.get("actQci1BlerTgt") == "true")) if on}


def _strip_lte(doc, site, dn):
    """Takes out what each cell runs; returns the cells and the features."""
    cells, features = [], set()
    enb = site.by_dn[dn]["p"]
    if enb.get("actPdcpRohc") == "true":
        features.add("rohc")
        doc.set(dn, "actPdcpRohc", "false", W)
    if enb.get("actVoLteNoEnDc") not in (None, "disabled"):
        features.add("noendc")
        doc.set(dn, "actVoLteNoEnDc", "disabled", W)
    for sub in site.child(dn, "LNBTS_FDD") + site.child(dn, "LNBTS_TDD"):
        doc.set(sub["dn"], "actConvVoice", "false", W)
    if doc.items(dn, "qciTab1"):
        doc.remove_item(dn, "qciTab1", 0, W)
    for m in site.child(dn, "LNCEL"):
        c, p = m["dn"], m["p"]
        mine = _lte_features(p)
        features |= mine
        cells.append(c)
        for k in ("harqMaxTrVoLteDl", "n310Qci1", "t310Qci1"):
            doc.unset(c, k, W)
        if "ttib" in mine:
            doc.set(c, "actTtiBundling", "false", W)
            for k in ["harqMaxTrUlTtiBundling", "actTtibRsc", "ttibMinUlPrb"] + [
                    k for rows in (voice.TTIB, voice.TTIB_SINR, voice.TTIB_DWELL, voice.TTIB_EXTRA) for k, _ in rows]:
                doc.unset(c, k, W)
            if p.get("actUlLnkAdp") == "fUlLa":
                for k in ("eUlLaLowMcsThr", "eUlLaLowPrbThr"):
                    doc.unset(c, k, W)
        if "grants" in mine:
            for k in ("maxNumVoLteProactUlGrantsPerTti", "voLteProactUlGrantPeriodRegTx",
                      "voLteProactUlGrantPeriodTtib"):
                doc.set(c, k, "0", W)
            for k, _ in voice.GRANTS:
                doc.unset(c, k, W)
        for f, switch, rows in (("evtt", "actQci1eVTT", "qci1eVTTConfig"), ("bler", "actQci1BlerTgt",
                                                                             "qci1BlerTgtConfig")):
            if f in mine:
                doc.set(c, switch, "false", W)
                for i in reversed(range(len(doc.items(c, rows)))):
                    doc.remove_item(c, rows, i, W)
    return cells, features


def _strip_nr(doc, site, dn):
    cells = [c["dn"] for c in site.child(dn, "NRCELL") if c["p"].get("actVoNR") == "true"]
    features = set()
    if doc.get(dn, "actRohc") == "true":
        features.add("rohc")
        doc.set(dn, "actRohc", "false", W)
    doc.unset(dn, "tRLFindForDUVoNR", W)
    for c in cells:
        p = site.by_dn[c]["p"]
        features |= {f for f, k, v in (("enhanced", "actEnhancedVoNR", "true"), ("la", "actTargetBlerVoNR", "true"),
                                       ("coverage", "actVoNRIncCodingGain", "true"),
                                       ("fallback", "voiceFBMode", "redirection")) if p.get(k) == v}
        for k, v in NR_SWITCHES.items():
            if doc.get(c, k) is not None:
                doc.set(c, k, v, W)
        for k in NR_VALUES:
            doc.unset(c, k, W)
    return cells, features


def _settings(site, dn, cells, side):
    """{(object, setting): value} for what the action writes."""
    out = {}
    if side == voice.LTE:
        for sub in site.child(dn, "LNBTS_FDD") + site.child(dn, "LNBTS_TDD"):
            out[(sub["dn"], "actConvVoice")] = sub["p"].get("actConvVoice")
        for k in ("actPdcpRohc", "actVoLteNoEnDc"):
            out[(dn, k)] = site.by_dn[dn]["p"].get(k)
        out[(dn, "qciTab1 qciSupp")] = next((r.get("qciSupp") for r in site.by_dn[dn]["lists"].get("qciTab1", [])),
                                            None)
        names, rows = list(LTE_SWITCHES) + LTE_VALUES, LTE_ROWS
    else:
        out[(dn, "actRohc")] = site.by_dn[dn]["p"].get("actRohc")
        out[(dn, "tRLFindForDUVoNR")] = site.by_dn[dn]["p"].get("tRLFindForDUVoNR")
        names, rows = list(NR_SWITCHES) + NR_VALUES, ()
    for c in cells:
        m = site.by_dn[c]
        for k in names:
            out[(c, k)] = m["p"].get(k)
        for k in rows:
            out[(c, k)] = m["lists"].get(k)
    return out


def round_trip(corpus, raws, index, failures, diffs):
    done = collections.Counter()
    for (source, name), raw in raws.items():
        ctx = Context(raw, name, source, corpus=lambda: corpus, release_index=lambda: index)
        site = ctx.site
        targets = [(voice.LTE, e) for e in voice._enbs(ctx)
                   if any(s["p"].get("actConvVoice") == "true"
                          for s in site.child(e["dn"], "LNBTS_FDD") + site.child(e["dn"], "LNBTS_TDD"))]
        targets += [(voice.NR, g) for g in voice._gnbs(ctx)
                    if any(c["p"].get("actVoNR") == "true" for c in site.child(g["dn"], "NRCELL"))]
        for side, node in targets:
            dn = node["dn"]
            doc = Doc(raw)
            cells, features = (_strip_lte if side == voice.LTE else _strip_nr)(doc, site, dn)
            if not cells:
                continue
            full = LTE_FULL if side == voice.LTE else NR_FULL
            exact = {c for c in cells if release_of(site.by_dn[c]["version"]) == voice.PROFILE_RELEASE[side]
                     and all(site.by_dn[c]["p"].get(k) == v for k, v in full.items())
                     and (side == voice.NR or (site.by_dn[c]["p"].get("maxNumVoLteProactUlGrantsPerTti") or "0") != "0")}
            before = _settings(site, dn, cells, side)
            stripped = Context(doc.raw(), name, source, corpus=lambda: corpus, release_index=lambda: index)
            inputs = {"target": f"{side}|{dn}", "cells": cells, "features": sorted(features)}
            if side == voice.NR:
                inputs["slices"] = [s["dn"] for s in site.child(dn, "SNSSAI")] if voice._slices_named(ctx, node) else []
            where = f"{name} {label(dn)}"
            try:
                out, plan = voice.plan(stripped, inputs)
            except PlanError as e:
                failures.append(f"{where}: round trip refused: {e.problems}")
                continue
            except Exception:
                failures.append(f"{where}: round trip crashed\n{traceback.format_exc()}")
                continue
            if new_findings(plan):
                failures.append(f"{where}: round trip new findings {new_findings(plan)[:3]}")
            after = _settings(Site(_load(out)), dn, cells, side)
            done[side] += len(cells)
            for (obj, k), v in before.items():
                if after.get((obj, k)) != v:
                    diffs[(side, k, str(v), str(after.get((obj, k))))] += 1
                    if obj in exact or (obj == dn and exact):
                        failures.append(f"{where}: {label(obj)} {k} came back {after.get((obj, k))}, was {v}")
    return done


def main(folders):
    corpus, raws, index = load(folders)
    counts, failures, diffs = collections.Counter(), [], collections.Counter()
    sweep(corpus, raws, index, counts, failures)
    done = round_trip(corpus, raws, index, failures, diffs)
    print(f"{len(raws)} files")
    for (kind, result), n in sorted(counts.items()):
        print(f"  {kind:14} {result:8} {n}")
    print(f"round trip: {done[voice.LTE]} LTE cells, {done[voice.NR]} NR cells rebuilt")
    for (side, k, was, now), n in sorted(diffs.items()):
        print(f"  differs {n:4}: {side} {k}: {was} -> {now}")
    print(f"{len(failures)} failures")
    for f in failures[:25]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    folders = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(folders))
