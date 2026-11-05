#!/usr/bin/env python3
"""
Corpus check for the neighbour eNB action (backend/app/actions/neighbour_enb.py,
and gnb_enb.py for a gNB).

1. Sweep: for every eNB in the given folders, plan a few neighbours from
   the other files (the first offered, the first with several cells, the
   first on another EARFCN, one that is already a neighbour) and one typed
   in. For every gNB, the first eNB offered, a co-sited one, one already a
   neighbour, the first with the X2 link, and one typed in (with X2, and
   with its own address, which must be refused). A crash fails; a refusal
   is counted with its reason. The result must parse, add no site-check
   error and no lte-relations finding, and planning it again must change
   nothing.
2. Round trip: every planned neighbour eNB (LNADJ whose LNADJLs weren't
   learned by ANR) is removed with its relations and typed back in, one
   cell at a time, with relations from the cells that had them. Every
   gNB's NRHOIR is removed with the NRLIM and NRREDRT on its EARFCN and
   typed back in on the cells that named it. What the action writes is
   compared with what the file had; differences are listed by class and
   parameter.

Usage: python3 scripts/neighbour_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if any file fails. Run from the repo root; no server needed.
"""
import collections
import hashlib
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.actions import Context, PlanError, gnb_enb, neighbour_enb as action  # noqa: E402
from app.actions.corpus import profile  # noqa: E402
from app.actions.doc import Doc, label, why  # noqa: E402
from app.actions.neighbours import own_addresses, plmn_text  # noqa: E402
from app.actions.sites import lte_cell  # noqa: E402
from app.parser import XmlParseError, parse_file  # noqa: E402

W = why("check", "round trip", "choice")


def load(folders):
    corpus, raws = [], {}
    for d in folders:
        src = "example" if os.path.basename(os.path.normpath(d)) == "example" else "scp"
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".xml"):
                continue
            path = os.path.join(d, f)
            raw = open(path, "rb").read()
            try:
                entry = profile(raw)
                parse_file(raw, f)
            except XmlParseError:
                continue
            corpus.append({"name": f, "source": src, "key": f"{src}:{f}", "mtime": os.path.getmtime(path),
                           "sha1": hashlib.sha1(raw).hexdigest(), **entry})
            raws[(src, f)] = raw
    return corpus, raws


def main(folders):
    corpus, raws = load(folders)
    index = {}
    for f in corpus:
        for (release, cls), names in f["params"].items():
            index.setdefault(release, {}).setdefault(cls, set()).update(names)
    ctx = lambda raw, src, name: Context(raw, name, src, corpus=lambda: corpus, release_index=lambda: index)
    counts, refusals, failures, diffs = collections.Counter(), collections.Counter(), [], collections.Counter()

    def check(c, src, name, inputs, where, kind):
        try:
            out, plan = action.plan(c, inputs)
        except PlanError as e:
            counts[(kind, "refused")] += 1
            for p in e.problems:
                refusals[p[:90]] += 1
            return None
        except Exception:
            failures.append(f"{where}: plan crashed\n{traceback.format_exc()}")
            return None
        counts[(kind, "ok")] += 1
        try:
            parse_file(out, name)
        except XmlParseError as e:
            failures.append(f"{where}: result doesn't parse: {e}")
            return None
        bad = [f["title"] for f in plan["check"]["new"] if f["severity"] == "error" or "no target" in f["title"]]
        if bad:
            failures.append(f"{where}: new site-check findings: {bad}")
        again = action.plan(ctx(out, src, name), inputs)[1]["changes"]
        if again:
            failures.append(f"{where}: not idempotent: {[(x['op'], x['dn'], x.get('param')) for x in again[:4]]}")
        return out

    # 1. Sweep.
    for (src, name), raw in raws.items():
        c = ctx(raw, src, name)
        try:
            if action.available(c):
                continue
            fields = {f["id"]: f for f in action.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: setup crashed\n{traceback.format_exc()}")
            continue
        for target in fields["target"]["options"]:
            if target["key"] in fields["nrCells"]["optionsByKey"]:
                sweep_gnb(c, src, name, fields, target, check, failures)
                continue
            opts = [o for o in fields["source"]["optionsByKey"][target["key"]] if o["value"] != action.MANUAL]
            mine = {o["label"].split("EARFCN ")[-1].split(" ")[0] for o in fields["from"]["optionsByKey"][target["key"]]}
            pick = {}
            for o in opts:
                cells = fields["cells"]["optionsByKey"][o["key"]]
                pick.setdefault("first", o)
                if len(cells) > 1:
                    pick.setdefault("several cells", o)
                if any(x["label"].split("EARFCN ")[-1].split(" ")[0] not in mine for x in cells):
                    pick.setdefault("other EARFCN", o)
                if "already a neighbour" in o["label"]:
                    pick.setdefault("already a neighbour", o)
            for kind, o in pick.items():
                check(c, src, name, {"target": target["value"], "source": o["value"]},
                      f"{name} {target['label']} <- {o['label']}", kind)
            manual = {"target": target["value"], "source": action.MANUAL, "enbId": "1048575", "ip": "10.250.250.9",
                      "plmn": fields["plmn"]["defaultByKey"][target["key"]] or "001-01", "lcrId": "7", "pci": "503",
                      "earfcn": fields["earfcn"]["defaultByKey"][target["key"]] or "100",
                      "tac": fields["tac"]["defaultByKey"][target["key"]] or "1", "bw": "10 MHz"}
            check(c, src, name, manual, f"{name} {target['label']} <- by hand", "by hand")

    # 2. Round trip of planned neighbours.
    trips = 0
    gnb_trips = round_trip_gnb(raws, ctx, failures, diffs)
    for (src, name), raw in raws.items():
        c = ctx(raw, src, name)
        site = c.site
        for lnadj in site.of("LNADJ"):
            adjls = site.child(lnadj["dn"], "LNADJL")
            if not adjls or any(m["p"].get("sourceOfData") for m in adjls) or not lnadj["p"].get("cPlaneIpAddr"):
                continue
            enb = lnadj["dn"].rsplit("/", 1)[0]
            nb_id = lnadj["p"].get("adjEnbId")
            rels = [r for cell in site.child(enb, "LNCEL") for r in site.child(cell["dn"], "LNREL")
                    if r["p"].get("ecgiAdjEnbId") == nb_id]
            doc = Doc(raw)
            doc.delete(lnadj["dn"], W)
            for r in rels:
                doc.delete(r["dn"], W)
            stripped = doc.raw()
            plmn = (lnadj.get("lists") or {}).get("plmnId", [{}])[0]
            plmn = plmn_text(plmn) if plmn else ""
            cur = stripped
            ok = True
            for adjl in adjls:
                lcr = adjl["p"].get("ecgiLcrId")
                froms = [r["dn"].rsplit("/", 1)[0] for r in rels if r["p"].get("ecgiLcrId") == lcr]
                if not froms:
                    continue
                inputs = {"target": enb, "source": action.MANUAL, "enbId": nb_id, "ip": lnadj["p"]["cPlaneIpAddr"],
                          "plmn": plmn, "lcrId": lcr, "pci": adjl["p"].get("phyCellId"),
                          "earfcn": adjl["p"].get("fDlEarfcn"), "tac": adjl["p"].get("tac"), "bw": "20 MHz",
                          "from": froms}
                try:
                    cur, _ = action.plan(ctx(cur, src, name), inputs)
                except Exception as e:
                    failures.append(f"{name} round trip of {label(lnadj['dn'])} cell {lcr}: {e}")
                    ok = False
                    break
            if not ok:
                continue
            trips += 1
            after = ctx(cur, src, name).site
            new_adj = next((m for m in after.child(enb, "LNADJ") if m["p"].get("adjEnbId") == nb_id), None)
            pairs = [(lnadj, new_adj)]
            related = {r["p"].get("ecgiLcrId") for r in rels}
            for adjl in adjls:
                if adjl["p"].get("ecgiLcrId") not in related:
                    continue  # no cell relates to it; the action always adds relations
                pairs.append((adjl, next((m for m in after.child(new_adj["dn"], "LNADJL")
                                          if m["p"].get("ecgiLcrId") == adjl["p"].get("ecgiLcrId")), None)
                              if new_adj else None))
            for r in rels:
                cell = r["dn"].rsplit("/", 1)[0]
                pairs.append((r, next((m for m in after.child(cell, "LNREL")
                                       if m["p"].get("ecgiAdjEnbId") == nb_id
                                       and m["p"].get("ecgiLcrId") == r["p"].get("ecgiLcrId")), None)))
            for old, new in pairs:
                if new is None:
                    diffs[(old["cls"], "missing", "", "")] += 1
                    continue
                for k in sorted(set(old["p"]) | set(new["p"])):
                    if old["p"].get(k) != new["p"].get(k):
                        diffs[(old["cls"], k, old["p"].get(k), new["p"].get(k))] += 1
                for ln in sorted(set(old.get("lists") or {}) | set(new.get("lists") or {})):
                    if (old.get("lists") or {}).get(ln) != (new.get("lists") or {}).get(ln):
                        diffs[(old["cls"], ln, "list", "differs")] += 1

    for key, n in sorted(counts.items()):
        print(f"{' / '.join(key)}: {n}")
    for reason, n in refusals.most_common():
        print(f"  refused {n}x: {reason}")
    print(f"round trip: {trips} planned neighbour eNBs, {gnb_trips} gNB handover carriers")
    for (cls, k, old, new), n in diffs.most_common():
        print(f"  differs {n}x: {cls}.{k}: file {old!r}, action {new!r}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failure{'s' if len(failures) != 1 else ''}")
    return 1 if failures else 0


def sweep_gnb(c, src, name, fields, target, check, failures):
    key = target["key"]
    opts = [o for o in fields["source"]["optionsByKey"][key] if o["value"] != gnb_enb.MANUAL]
    pick = {}
    for o in opts:
        pick.setdefault("gNB: first", o)
        if o["value"].startswith("here|"):
            pick.setdefault("gNB: co-sited", o)
        if "already a neighbour" in o["label"]:
            pick.setdefault("gNB: already a neighbour", o)
    for kind, o in pick.items():
        check(c, src, name, {"target": target["value"], "source": o["value"], "x2": []},
              f"{name} {target['label']} <- {o['label']}", kind)
    with_ip = next((o for o in opts if "X2 C-plane not in" not in " ".join(o.get("details", []))), None)
    if with_ip:
        check(c, src, name, {"target": target["value"], "source": with_ip["value"], "x2": ["x2"]},
              f"{name} {target['label']} <- {with_ip['label']} with X2", "gNB: with X2")
    manual = {"target": target["value"], "source": gnb_enb.MANUAL, "enbId": "1048575",
              "plmn": fields["plmn"]["defaultByKey"].get(key) or "001-01",
              "earfcn": fields["earfcn"]["defaultByKey"].get(key) or "66786", "x2": []}
    check(c, src, name, manual, f"{name} {target['label']} <- by hand", "gNB: by hand")
    check(c, src, name, {**manual, "x2": ["x2"], "enbIp": "10.250.250.9"},
          f"{name} {target['label']} <- by hand with X2", "gNB: by hand with X2")
    own = sorted(own_addresses(c.site))
    if own:
        try:
            action.plan(c, {**manual, "x2": ["x2"], "enbIp": own[0]})
            failures.append(f"{name} {target['label']}: its own address {own[0]} not refused")
        except PlanError:
            pass


def round_trip_gnb(raws, ctx, failures, diffs):
    """Each NRHOIR out with the NRLIM and NRREDRT on its EARFCN, then typed
    back in on the cells that named it."""
    trips = 0
    for (src, name), raw in raws.items():
        site = ctx(raw, src, name).site
        for hoir in site.of("NRHOIR"):
            gnb = hoir["dn"].rsplit("/", 1)[0]
            e = hoir["p"].get("earfcnValue")
            cells = [m for m in site.child(gnb, "NRCELL") if hoir["dn"] in (m.get("simple") or {}).get("nrhoirDNList", [])]
            if not e or not cells:
                continue
            doc = Doc(raw)
            old = [hoir] + [m for m in site.of("NRLIM", gnb) if m["p"].get("carrierFreq") == e]
            old += [m for c in cells for m in site.child(c["dn"], "NRREDRT") if m["p"].get("redirFreqEutra") == e]
            for m in old:
                doc.delete(m["dn"], W)
            for c in cells:
                doc.remove_value(c["dn"], "nrhoirDNList", hoir["dn"], W)
            plmn = next((m["p"] for m in site.child(gnb, "NRPLMN") if m["p"].get("mcc")), None)
            inputs = {"target": gnb, "source": gnb_enb.MANUAL, "enbId": "1", "plmn": plmn_text(plmn) or "001-01",
                      "earfcn": e, "nrCells": [c["dn"] for c in cells], "x2": []}
            try:
                out, _ = action.plan(ctx(doc.raw(), src, name), inputs)
            except Exception as ex:
                failures.append(f"{name} round trip of {label(hoir['dn'])}: {ex}")
                continue
            trips += 1
            after = ctx(out, src, name).site
            for m in old:
                parent = m["dn"].rsplit("/", 1)[0]
                field = {"NRHOIR": "earfcnValue", "NRLIM": "carrierFreq", "NRREDRT": "redirFreqEutra"}[m["cls"]]
                new = next((x for x in after.child(parent, m["cls"]) if x["p"].get(field) == e), None)
                if new is None:
                    diffs[(m["cls"], "missing", "", "")] += 1
                    continue
                for k in sorted(set(m["p"]) | set(new["p"])):
                    if m["p"].get(k) != new["p"].get(k):
                        diffs[(m["cls"], k, m["p"].get(k), new["p"].get(k))] += 1
                for ln in sorted(set(m.get("lists") or {}) | set(new.get("lists") or {})):
                    if (m.get("lists") or {}).get(ln) != (new.get("lists") or {}).get(ln):
                        diffs[(m["cls"], ln, "list", "differs")] += 1
            for c in cells:
                if hoir["dn"] not in (after.by_dn[c["dn"]].get("simple") or {}).get("nrhoirDNList", []) and not any(
                        after.by_dn.get(d, {}).get("p", {}).get("earfcnValue") == e
                        for d in (after.by_dn[c["dn"]].get("simple") or {}).get("nrhoirDNList", [])):
                    diffs[("NRCELL", "nrhoirDNList", "names it", "doesn't")] += 1
    return trips


if __name__ == "__main__":
    args = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(args))
