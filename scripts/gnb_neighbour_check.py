#!/usr/bin/env python3
"""
Corpus check for the neighbour gNB action (backend/app/actions/
neighbour_gnb.py: Xn on a gNB, and endc_gnb.py on an eNB).

1. Sweep:
   - every eNB gets a few gNBs from the other files (the first offered, the
     first with several cells, one that is already its neighbour) and one
     typed in, with relations and without, and with its NR carrier;
   - every gNB gets the first gNB offered and one typed in, and a learned
     (gnbControlled) XNLINK planned again must turn oamControlled.
   A crash fails; a refusal is counted with its reason. The result must
   parse and add no site-check error, and planning it again must change
   nothing. The BTS's own address must be refused.
2. Round trip: every LNADJGNB with an address is removed with its
   relations and typed back in; every oamControlled XNLINK likewise. What
   the action writes is compared with what the file had; differences are
   listed by class and parameter.

Usage: python3 scripts/gnb_neighbour_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if any file fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from neighbour_check import load  # noqa: E402

from app.actions import Context, PlanError, endc_gnb, neighbour_gnb  # noqa: E402
from app.actions.doc import Doc, label, why  # noqa: E402
from app.actions.neighbours import lte_enbs, own_addresses, plmn_of, plmn_text  # noqa: E402
from app.parser import XmlParseError, parse_file  # noqa: E402

W = why("check", "round trip", "choice")


def main(folders):
    corpus, raws = load(folders)
    index = {}
    for f in corpus:
        for (release, cls), names in f["params"].items():
            index.setdefault(release, {}).setdefault(cls, set()).update(names)
    ctx = lambda raw, src, name: Context(raw, name, src, corpus=lambda: corpus, release_index=lambda: index)
    counts, refusals, failures, diffs = collections.Counter(), collections.Counter(), [], collections.Counter()
    notes = collections.Counter()

    action = neighbour_gnb

    def check(side, c, src, name, inputs, where, kind):
        try:
            out, plan = action.plan(c, inputs)
        except PlanError as e:
            counts[(side, kind, "refused")] += 1
            for p in e.problems:
                refusals[(side, p[:90])] += 1
            return None, None
        except Exception:
            failures.append(f"{where}: plan crashed\n{traceback.format_exc()}")
            return None, None
        counts[(side, kind, "ok")] += 1
        for n in plan["notes"]:
            notes[(side, n.split(":")[0][:70])] += 1
        try:
            parse_file(out, name)
        except XmlParseError as e:
            failures.append(f"{where}: result doesn't parse: {e}")
            return None, None
        bad = [f["title"] for f in plan["check"]["new"] if f["severity"] == "error"]
        if bad:
            failures.append(f"{where}: new site-check errors: {bad}")
        again = action.plan(ctx(out, src, name), inputs)[1]["changes"]
        if again:
            failures.append(f"{where}: not idempotent: {[(x['op'], x['dn'], x.get('param')) for x in again[:4]]}")
        return out, plan

    def refused(c, inputs, where):
        try:
            action.plan(c, inputs)
        except PlanError:
            return
        failures.append(f"{where}: not refused")

    # 1. Sweep.
    for (src, name), raw in raws.items():
        c = ctx(raw, src, name)
        own = sorted(own_addresses(c.site))
        try:
            if action.available(c):
                continue
            fields = {f["id"]: f for f in action.setup(c)["fields"]}
        except Exception:
            failures.append(f"{name}: setup crashed\n{traceback.format_exc()}")
            continue
        for target in fields["target"]["options"]:
            where = f"{name} {target['label']}"
            lte = target["key"] in fields["from"]["optionsByKey"]
            side, manual_value = ("eNB", endc_gnb.MANUAL) if lte else ("gNB", neighbour_gnb.MANUAL)
            opts = [o for o in fields["source"]["optionsByKey"][target["key"]] if o["value"] != manual_value]
            pick = {}
            for o in opts:
                pick.setdefault("first", o)
                if lte and len(fields["cells"]["optionsByKey"].get(o["key"], [])) > 1:
                    pick.setdefault("several cells", o)
                if o["value"].startswith("here|"):
                    pick.setdefault("co-sited", o)
                if "already a neighbour" in o["label"]:
                    pick.setdefault("already a neighbour", o)
            for kind, o in pick.items():
                check(side, c, src, name, {"target": target["value"], "source": o["value"]},
                      f"{where} <- {o['label']}", kind)
            if lte:
                manual = {"target": target["value"], "source": manual_value, "gnbId": "4194303",
                          "idLength": fields["idLength"]["defaultByKey"][target["key"]] or "22",
                          "ip": "10.250.250.9", "plmn": fields["plmn"]["defaultByKey"][target["key"]] or "001-01"}
                check(side, c, src, name, {**manual, "lcrIds": "1, 2"}, f"{where} <- by hand", "by hand")
                check(side, c, src, name, manual, f"{where} <- by hand, X2 only", "by hand, X2 only")
                check(side, c, src, name, {**manual, "ssb": "502110", "band": "41", "scs": "30 kHz"},
                      f"{where} <- by hand, with its carrier", "by hand, with its carrier")
            else:
                manual = {"target": target["value"], "source": manual_value, "xnIp": "10.250.250.9"}
                check(side, c, src, name, manual, f"{where} <- by hand", "by hand")
                check(side, c, src, name, {**manual, "ssb": "520110", "band": "41", "scs": "30 kHz"},
                      f"{where} <- by hand, on another carrier", "by hand, on another carrier")
                learned = next((m for m in c.site.child(target["value"], "XNLINK")
                                if m["p"].get("cPlaneIpAddrCtrl") == "gnbControlled"), None)
                if learned:
                    out, plan = check(side, c, src, name, {**manual, "xnIp": learned["p"]["cPlaneIpAddr"]},
                                      f"{where} <- learned {label(learned['dn'])}", "learned link")
                    if plan and ("set", "cPlaneIpAddrCtrl") not in [(x["op"], x.get("param")) for x in plan["changes"]]:
                        failures.append(f"{where}: learned {label(learned['dn'])} planned again doesn't turn "
                                        "oamControlled")
                    elif plan and any(x["op"] != "set" or x["dn"] != target["value"]
                                      for x in plan["changes"] if x.get("param") != "cPlaneIpAddrCtrl"
                                      and x.get("class") != "NRANR"):
                        failures.append(f"{where}: learned {label(learned['dn'])} planned again adds more than the "
                                        "gNB's switches and NRANR")
            if own:
                extra = {"gnbId": "4194303", "idLength": "22", "plmn": "001-01", "ip": own[0]} if lte else \
                    {"xnIp": own[0]}
                refused(c, {"target": target["value"], "source": manual_value, **extra},
                        f"{where} <- its own address {own[0]}")

    # 2. Round trip.
    trips = collections.Counter()
    for (src, name), raw in raws.items():
        site = ctx(raw, src, name).site
        with_cells = {m["dn"] for m in lte_enbs(site)}
        for adj in site.of("LNADJGNB"):
            ip = adj["p"].get("cPlaneIpAddr")
            enb = adj["dn"].rsplit("/", 1)[0]
            if not ip or enb not in with_cells:
                continue
            plmn = plmn_of(adj, "plmnId")
            gnb_id, length = adj["p"].get("adjGnbId"), adj["p"].get("adjGnbIdLength")
            rels = [r for cell in site.child(enb, "LNCEL") for r in site.child(cell["dn"], "LNRELGNBCELL")
                    if gnb_id and length and int(r["p"]["nrCellId"]) >> (36 - int(length)) == int(gnb_id)]
            if not (gnb_id and length and plmn):
                continue  # what the eNB learned over X2 isn't in the file; nothing to type back in
            doc = Doc(raw)
            for m in [adj] + rels:
                doc.delete(m["dn"], W)
            lcrs = sorted({str(int(r["p"]["nrCellId"]) & ((1 << (36 - int(length))) - 1)) for r in rels}, key=int)
            froms = sorted({r["dn"].rsplit("/", 1)[0] for r in rels})
            inputs = {"target": enb, "source": endc_gnb.MANUAL, "gnbId": gnb_id, "idLength": length, "ip": ip,
                      "plmn": plmn_text(plmn), "lcrIds": ", ".join(lcrs), **({"from": froms} if froms else {})}
            try:
                out, _ = neighbour_gnb.plan(ctx(doc.raw(), src, name), inputs)
            except Exception as e:
                failures.append(f"{name} round trip of {label(adj['dn'])}: {e}")
                continue
            trips["LNADJGNB"] += 1
            after = ctx(out, src, name).site
            new = next((m for m in after.child(enb, "LNADJGNB") if m["p"].get("cPlaneIpAddr") == ip), None)
            pairs = [(adj, new)]
            for r in rels:
                cell = r["dn"].rsplit("/", 1)[0]
                pairs.append((r, next((m for m in after.child(cell, "LNRELGNBCELL")
                                       if m["p"].get("nrCellId") == r["p"]["nrCellId"]), None)))
            compare(pairs, diffs)
        for link in site.of("XNLINK"):
            if link["p"].get("cPlaneIpAddrCtrl") != "oamControlled":
                continue
            gnb = link["dn"].rsplit("/", 1)[0]
            doc = Doc(raw)
            doc.delete(link["dn"], W)
            inputs = {"target": gnb, "source": neighbour_gnb.MANUAL, "xnIp": link["p"]["cPlaneIpAddr"]}
            try:
                out, _ = neighbour_gnb.plan(ctx(doc.raw(), src, name), inputs)
            except Exception as e:
                failures.append(f"{name} round trip of {label(link['dn'])}: {e}")
                continue
            trips["XNLINK"] += 1
            after = ctx(out, src, name).site
            compare([(link, next((m for m in after.child(gnb, "XNLINK")
                                  if m["p"].get("cPlaneIpAddr") == link["p"]["cPlaneIpAddr"]), None))], diffs)

    for key, n in sorted(counts.items()):
        print(f"{' / '.join(key)}: {n}")
    for (aid, reason), n in refusals.most_common():
        print(f"  {aid} refused {n}x: {reason}")
    for (aid, note), n in notes.most_common():
        print(f"  {aid} note {n}x: {note}")
    print(f"round trip: {dict(trips)}")
    for (cls, k, old, new), n in diffs.most_common():
        print(f"  differs {n}x: {cls}.{k}: file {old!r}, action {new!r}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(failures)} failure{'s' if len(failures) != 1 else ''}")
    return 1 if failures else 0


def compare(pairs, diffs):
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


if __name__ == "__main__":
    args = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(args))
