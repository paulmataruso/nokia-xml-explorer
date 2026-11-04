#!/usr/bin/env python3
"""
Corpus check for the renumber action (backend/app/actions/renumber.py) and
Doc.renumber.

Round trip, in every file, on the 40 objects with the most links and one
object of every class (the BTS root included): renumbered to a free number,
every reference-map link (references and id links) touching the object or
anything under it touches the new numbers instead, and every other link is
unchanged; renumbered back, the file is byte for byte what it was.
Sweep, through the action with the site check, in every file: the 3 objects
with the most links each to a free number, and every class with gaps
numbered in order (up to 5 per file): no crash, no new site-check error or
warning, and numbering in order again is refused as done. The refusals are
checked once per file that has them: NRDRB-1 (the default bearer), an LCELL
or LCELNR, number 1 for an NRDRB_5QI that doesn't map 5QI 1, a number
taken, a repeated distName.
Tidy (backend/app/actions/tidy.py), on every file it is offered on, both
ways of counting, every class picked: no crash, no new site-check error or
warning, every link kept under the combined renumbering, nothing left to
tidy. A production file (a gNB whose mappings name slices: Nokia's own
numbering, which tidy follows) must be left as it is. The counts say how
many mappings end up numbered by their value.
A runtime value naming a number nothing had may name a renumbered object
afterwards; those new links are allowed (the BTS reports them again).

Usage: python3 scripts/renumber_check.py [folder ...]
       (default: example/ and scp/, whichever exist)
Exit status 1 if anything fails. Run from the repo root; no server needed.
"""
import collections
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.actions import Context, PlanError, renumber, tidy  # noqa: E402
from app.actions.doc import Doc, instance, label, why  # noqa: E402
from app.actions.links import _runtime  # noqa: E402
from app.actions.qos_files import summary  # noqa: E402
from app.ca import _load  # noqa: E402
from app.refmap import build  # noqa: E402
from cell_check import load  # noqa: E402

W = why("check", "round trip", "choice")
SAMPLE = 40


def signature(doc):
    """What a byte comparison would see, without serialising: every element's attributes and text."""
    return [(el.tag, tuple(sorted(el.attrib.items())), (el.text or "").strip()) for el in doc.root.iter()]


def links(raw):
    return collections.Counter((e["s"], e["t"], e["via"], e["kind"]) for e in build(_load(raw))["edges"])


def mover(old, new):
    return lambda v: new + v[len(old):] if v == old or v.startswith(old + "/") else v


def free(doc, dn):
    """A free number for dn; for an eNB, not a neighbour's id (the action refuses those)."""
    n = max(int(instance(d)) for d in doc.mos if d.rpartition("/")[0] == dn.rpartition("/")[0]
            and label(d).rsplit("-", 1)[0] == label(dn).rsplit("-", 1)[0] and instance(d).isdigit()) + 1
    while str(n) in renumber.neighbour_enbs(doc, dn):
        n += 1
    return renumber._numbered(dn, str(n))


def movable(dn):
    cls = label(dn).rsplit("-", 1)[0]
    return (instance(dn).isdigit() and not _runtime(dn) and cls not in renumber.BY_LCR
            and (cls, instance(dn)) not in renumber.FIXED)


def round_trip(name, raw, counts, failures):
    doc = Doc(raw)
    original = doc.raw()
    sig = signature(doc)
    before = links(original)
    degree = collections.Counter()
    for s, t, _, _ in before:
        degree[s] += 1
        degree[t] += 1
    picks = [d for d, _ in degree.most_common() if d in doc.mos and movable(d)][:SAMPLE]
    seen = {label(d).rsplit("-", 1)[0] for d in picks}
    for d in doc.mos:
        cls = label(d).rsplit("-", 1)[0]
        if cls not in seen and movable(d):
            seen.add(cls)
            picks.append(d)
    for dn in picks:
        new = free(doc, dn)
        try:
            doc.renumber(dn, new, W)
            move = mover(dn, new)
            want = collections.Counter({(move(s), move(t), via, kind): n for (s, t, via, kind), n in before.items()})
            got = links(doc.raw())
            if differ(want, got):
                lost = list((want - got).elements())[:2]
                extra = list((got - want).elements())[:2]
                failures.append(f"{name}: {label(dn)} -> {label(new)}: links differ; lost {lost}, new {extra}")
            doc.renumber(new, dn, W)
            if signature(doc) != sig:
                failures.append(f"{name}: {label(dn)} -> {label(new)} and back: the file changed")
                doc = Doc(raw)
            counts["round trips"] += 1
        except Exception:
            failures.append(f"{name}: {label(dn)}: crashed\n{traceback.format_exc()}")
            doc = Doc(raw)
    if doc.raw() != original:
        failures.append(f"{name}: after the round trips the file isn't byte for byte what it was")


def differ(want, got):
    """Links lost, or new ones other than from runtime objects."""
    return bool(want - got) or any(not _runtime(e[0]) for e in (got - want))


def new_findings(plan):
    return [f["title"] for f in plan["check"]["new"] if f["severity"] in ("error", "warning")]


def sweep(name, source, raw, counts, failures):
    ctx = Context(raw, name, source)
    doc = Doc(raw)
    repeated = {d for d, n in collections.Counter(m["dn"] for m in ctx.mos).items() if n > 1}
    if repeated:  # the action refuses those, and anything around them
        counts["files with a repeat"] += 1
        d = sorted(repeated)[0]
        try:
            renumber.plan(ctx, {"object": d, "scope": renumber.ONE, "number": instance(free(doc, d))})
            failures.append(f"{name}: {label(d)}, repeated, wasn't refused")
        except PlanError as e:
            if "more than once" not in " ".join(e.problems):
                failures.append(f"{name}: {label(d)}: refused for another reason: {e.problems}")
            counts["refusals"] += 1
        return
    degree = collections.Counter()
    for (s, t, _, _), n in links(raw).items():
        degree[s] += n
        degree[t] += n
    for dn in [d for d, _ in degree.most_common() if d in doc.mos and movable(d)][:3]:
        try:
            _, plan = renumber.plan(ctx, {"object": dn, "scope": renumber.ONE, "number": instance(free(doc, dn))})
            counts["one"] += 1
            if new_findings(plan):
                failures.append(f"{name}: {label(dn)}: new findings {new_findings(plan)[:3]}")
        except Exception:
            failures.append(f"{name}: {label(dn)}: crashed\n{traceback.format_exc()}")
    groups = collections.defaultdict(list)
    for d in doc.mos:
        if movable(d):
            groups[(d.rpartition("/")[0], label(d).rsplit("-", 1)[0])].append(d)
    gappy = []
    for (parent, cls), members in groups.items():
        nums = sorted(int(instance(d)) for d in members)
        if len(nums) > 1 and nums != list(range(nums[0], nums[0] + len(nums))):
            gappy.append(members[0])
    for dn in gappy[:5]:
        try:
            out, plan = renumber.plan(ctx, {"object": dn, "scope": renumber.ALL})
        except PlanError as e:
            if "numbered so already" not in " ".join(e.problems):  # the reserved 1 can leave a gap that is no gap
                failures.append(f"{name}: in order from {label(dn)}: refused {e.problems}")
            continue
        except Exception:
            failures.append(f"{name}: in order from {label(dn)}: crashed\n{traceback.format_exc()}")
            continue
        counts["in order"] += 1
        if new_findings(plan):
            failures.append(f"{name}: in order from {label(dn)}: new findings {new_findings(plan)[:3]}")
        try:
            renumber.plan(Context(out, name, source), {"object": plan["changes"][0]["new"], "scope": renumber.ALL})
            failures.append(f"{name}: in order from {label(dn)}: a repeat wasn't refused")
        except PlanError:
            counts["repeat refused"] += 1
    refusals = []
    drb1 = next((d for d in doc.mos if label(d) == "NRDRB-1"), None)
    if drb1:
        refusals.append(({"object": drb1, "scope": renumber.ONE, "number": "9"}, "default bearer"))
    lcell = next((d for d in doc.mos if label(d).rsplit("-", 1)[0] in renumber.BY_LCR), None)
    if lcell:
        refusals.append(({"object": lcell, "scope": renumber.ONE, "number": "99"}, "lcrId"))
    q = next((d for d in doc.mos if label(d).startswith("NRDRB_5QI-") and instance(d) != "1"
              and doc.values(d, "fiveqiValueList") != ["1"]), None)
    if q:
        refusals.append(({"object": q, "scope": renumber.ONE, "number": "1"}, "the mapping of 5QI 1"))
    taken = next(((a, b) for a in doc.mos for b in [renumber._numbered(a, "1")]
                  if movable(a) and a != b and b in doc.mos), None)
    if taken:
        refusals.append(({"object": taken[0], "scope": renumber.ONE, "number": "1"}, "exists already"))
    for inputs, words in refusals:
        try:
            renumber.plan(ctx, inputs)
            failures.append(f"{name}: {label(inputs['object'])} to {inputs['number']} wasn't refused")
        except PlanError as e:
            if words not in " ".join(e.problems):
                failures.append(f"{name}: {label(inputs['object'])}: refused for another reason: {e.problems}")
            counts["refusals"] += 1


def tidied(name, source, raw, counts, failures):
    ctx = Context(raw, name, source)
    if any(any(p["slices"] for p in g["profiles"]) for g in summary(ctx.mos)["gnbs"]):
        counts["tidy: production files"] += 1
        moved = tidy.plan_numbers(ctx, Doc(raw))
        if moved:
            failures.append(f"{name}: tidy would renumber a production file: {sorted(moved)[:3]}")
        return
    if tidy.available(ctx):
        counts["tidy: nothing to do"] += 1
        return
    field = next(f for f in tidy.setup(ctx)["fields"] if f["id"] == "groups")
    for start, options in field["optionsByKey"].items():
        where = f"{name}: tidy {start}"
        if not options:
            continue
        try:
            out, plan = tidy.plan(ctx, {"start": start, "groups": [o["value"] for o in options]})
        except Exception:
            failures.append(f"{where}: crashed\n{traceback.format_exc()}")
            continue
        counts[f"tidy {start}"] += 1
        if new_findings(plan):
            failures.append(f"{where}: new findings {new_findings(plan)[:3]}")
        groups = tidy.plan_numbers(ctx, Doc(raw), None, start)
        order = sorted(groups.values(), key=lambda m: -next(iter(m)).count("/"))

        def final(v):  # each class's renumbering at once, children's before their parents'
            for moves in order:
                o = next((o for o in moves if v == o or v.startswith(o + "/")), None)
                if o:
                    v = moves[o] + v[len(o):]
            return v
        want = collections.Counter({(final(a), final(b), via, kind): k for (a, b, via, kind), k in links(raw).items()})
        got = links(out)
        if differ(want, got):
            failures.append(f"{where}: links differ; lost {list((want - got).elements())[:2]}, "
                            f"new {list((got - want).elements())[:2]}")
        doc = Doc(out)
        for cls, values in tidy.MAPPINGS.items():
            for d in doc.of_class(cls):
                by_value = doc.values(d, values) == [instance(d)]
                counts[f"tidy {start}: {cls} " + ("numbered by value" if by_value else "not by value")] += 1
        again = Context(out, name, source)
        if start == tidy.FROM_ONE and not tidy.available(again):
            left = tidy.plan_numbers(again, Doc(out), None, start)
            failures.append(f"{where}: still to tidy afterwards: {sorted(left)[:3]}")


def main(folders):
    corpus, raws = load(folders)
    counts, failures = collections.Counter(), []
    for (source, name), raw in raws.items():
        round_trip(name, raw, counts, failures)
        sweep(name, source, raw, counts, failures)
        tidied(name, source, raw, counts, failures)
    print(f"{len(raws)} files: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"{len(failures)} failures")
    for f in failures[:30]:
        print("  " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    args = sys.argv[1:] or [d for d in ("example", "scp") if os.path.isdir(d)]
    sys.exit(main(args))
