"""
Replace a gNB's QoS mappings with production's: the clean-out the owner
asked for (2026-11-03: "when I go to add a cannaed feature, it should
remove the mess that is in the SCP first"; the answers: remove every
mapping and the bearers and profiles nothing else uses, keep NRDRB-1, write
the set numbered as Nokia's production gNBs number it, the canned value
wins and the review lists each old value).

replace_nr() works on one gNB and side (SA: NRDRB_5QI, EN-DC: NRDRB_QCI):
- Replaced: the side's mappings whose values are all among `values` (None:
  every mapping of the side). With them go each NRDRB only replaced
  mappings name (never NRDRB-1, the default bearer), and each NRDRB_MAC,
  NRDRB_PDCP, NRDRB_RLC_AM or _UM only those bearers name. Replacing the
  whole side also takes the bearers and profiles nothing names. NRDRX
  stays: the cells name it too, and the DRX action owns it.
- Written: each value with production's template (one production has no
  template for keeps its own bearer settings), numbered as tidy.py numbers
  the chain: NRDRB_5QI-<5QI> (a second mapping of 5QI 1-9 20 above),
  NRDRB-<10 + 5QI> (a second's: its mapping's number; QCI q: NRDRB-q), each
  profile at production's number for it, shared as production shares them.
  A number something kept holds sends the object to the lowest free one.
- The slices are the site's: a new mapping names what the one it replaces
  named (the k-th mapping of a value, the k-th now), else `slices`.
- It converges instead of deleting and recreating: an object already on
  a number it is written to keeps it and gets the template's values, so a
  gNB numbered and set as production comes out unchanged. A parameter the
  template doesn't set is removed on the template's release (25R2, where
  production's object is the whole object) and kept on others, in a note.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ..parser import _local
from .doc import Doc, instance, label, natural, why
from .renumber import _cls
from .qos import MAPPING, NAME, SA, TEMPLATE_RELEASE, TEMPLATES, _el_values, _Nr
from .qos_files import bearer as bearer_of
from .tidy import BEARER, PROFILES, REPEAT

DEFAULT_BEARER = "1"


def _full(gnb: str, value: Optional[str]) -> Optional[str]:
    """A reference as a distName: one lab export writes them relative to the gNB."""
    return value if not value or value.startswith("MRBTS-") else f"{gnb}/{value}"


def _namers(doc: Doc, gnb: str) -> dict[str, set[str]]:
    """distName -> the objects with a value naming it."""
    out: dict[str, set[str]] = defaultdict(set)
    for holder, el in doc.mos.items():
        for p in el.iter():
            if p is el or _local(p.tag) != "p":
                continue
            text = (p.text or "").strip()
            if text in doc.mos:
                out[text].add(holder)
            elif text and holder.startswith(gnb + "/") and f"{gnb}/{text}" in doc.mos:
                out[f"{gnb}/{text}"].add(holder)
    return out


def _labels(dns) -> str:
    return ", ".join(label(d) for d in sorted(dns, key=natural))


class _Replace:
    def __init__(self, ctx, doc: Doc, side: str, gnb: dict):
        self.ctx, self.doc, self.side, self.g = ctx, doc, side, gnb["dn"]
        self.nr = _Nr(ctx, doc, gnb, side)
        self.cls, self.list = MAPPING[side]
        self.kind = "5qi" if side == SA else "qci"
        self.name = NAME[side]
        self.strict = self.nr.release == TEMPLATE_RELEASE
        self.gone: set[str] = set()
        self.desired: dict[str, dict] = {}  # distName -> {cls, content, refs, why}

    def held(self, cls: str) -> set[int]:
        """The numbers of a class a written object can't take: kept objects' and those planned."""
        out = {int(instance(d)) for d in self.doc.children(self.g, cls) if d not in self.gone
               and instance(d).isdigit()}
        return out | {int(instance(d)) for d, x in self.desired.items() if x["cls"] == cls}

    def lowest(self, cls: str, start: int) -> int:
        n, held = start, self.held(cls)
        while n in held:
            n += 1
        return n

    def want(self, cls: str, n: int, content: dict, refs: dict, reason: str, own: bool) -> str:
        """Plans dn; `own`: production's number for it, so an object there keeps its role."""
        dn = f"{self.g}/{cls}-{n}"
        self.desired[dn] = {"cls": cls, "content": content, "refs": refs, "why": reason, "own": own}
        return dn

    def part(self, cls: str, part: dict, value: str, fallback: bool) -> Optional[str]:
        """A profile with the template's values. First (`fallback` False) only on production's number for it:
        planned there already, there with those values, or new there; None if something else holds it. Then
        one planned or kept with those values, else a new one on the lowest free number."""
        if cls not in PROFILES.values():  # NRDRX: the DRX action's; qos.py's rules
            return self.nr.part(cls, part)
        content = self.nr.filtered(cls, part)
        inst = part.get("inst")
        reason = f"The {cls} profile of production's {self.name} {value} template"
        if not fallback:
            # Production has profiles with the same values under two numbers (NRDRB_PDCP-3 and -5), each
            # bearer naming its own: the number decides, not the values.
            at = f"{self.g}/{cls}-{inst}" if inst and inst.isdigit() else None
            if at is None:
                return None
            if at in self.desired:
                return at if self.desired[at]["content"] == content else None
            if self.doc.exists(at) and at not in self.gone:
                return at if _el_values(self.doc, at) == content else None
            return self.want(cls, int(inst), content, {}, f"{reason}, on its production number {inst}.", True)
        for dn, x in self.desired.items():
            if x["cls"] == cls and x["content"] == content:
                return dn
        same = [d for d in self.doc.children(self.g, cls) if d not in self.gone
                and _el_values(self.doc, d) == content]
        if same:
            self.nr.reused.append(label(same[0]))
            return same[0]
        n = self.lowest(cls, 1)
        return self.want(cls, n, content, {}, f"{reason}; " + (f"{inst}, its production number, is taken, so {n}."
                                                               if inst else f"the lowest free number, {n}."), False)

    def converge(self, dn: str, x: dict, w: dict) -> list[str]:
        """The object at dn set to x: the canned values win. Returns what it keeps that x doesn't set."""
        doc, now, kept = self.doc, _el_values(self.doc, dn), []
        want = {**x["content"]["p"], **x["refs"]}
        for k, v in sorted(want.items()):
            if not (k in x["refs"] and _full(self.g, now["p"].get(k)) == v):
                doc.set(dn, k, v, w)
        for k in sorted(set(now["p"]) - set(want)):
            if self.strict:
                doc.unset(dn, k, w)
            else:
                kept.append(k)
        for name, values in sorted(x["content"]["simple"].items()):
            doc.set_values(dn, name, values, w)
        for name in sorted(set(now["simple"]) - set(x["content"]["simple"])):
            if self.strict:
                doc.set_values(dn, name, [], w)
            else:
                kept.append(name)
        for name in sorted(set(now["rows"]) | set(x["content"]["rows"])):
            rows = x["content"]["rows"].get(name)
            if rows is None and not self.strict:
                kept.append(name)
                continue
            if now["rows"].get(name, []) != (rows or []):
                for i in reversed(range(len(now["rows"].get(name, [])))):
                    doc.remove_item(dn, name, i, w)
                for row in rows or []:
                    doc.add_item(dn, name, sorted(row.items()), w)
        return kept

    def create(self, dn: str, x: dict, w: dict) -> None:
        cls, content = x["cls"], x["content"]
        params = sorted([*content["p"].items(), *x["refs"].items()])
        self.doc.create(self.g, cls, instance(dn), params, full_class=self.nr.full_class(cls),
                        version=None if self.doc.of_class(cls) else self.nr.gnb["version"], w=w)
        for name, values in sorted(content["simple"].items()):
            if values:
                self.doc.set_values(dn, name, values, w)
        for name, rows in sorted(content["rows"].items()):
            for row in rows:
                self.doc.add_item(dn, name, sorted(row.items()), w)


def replace_nr(ctx, doc: Doc, side: str, gnb: dict, values: Optional[set[str]] = None,
               keep: frozenset = frozenset(), slices=()) -> dict:
    """Replaces the side's mappings of `values` (None: all of them, writing
    production's set and the values in `keep`) on one gNB. Returns
    {notes, written (the mappings, in value order), removed, values}."""
    r = _Replace(ctx, doc, side, gnb)
    g, built, name = r.g, TEMPLATES.get(r.kind, {}), r.name
    maps = doc.children(g, r.cls)
    held_values = {m: doc.values(m, r.list) for m in maps}
    if values is None:
        replaced = list(maps)
        extras = sorted({v for vs in held_values.values() for v in vs if v not in built}, key=int)
        write = sorted(set(built) | (set(keep) & set(extras)), key=int)
    else:
        replaced = [m for m in maps if held_values[m] and set(held_values[m]) <= values]
        extras = []
        write = sorted(values, key=int)
    notes: list[str] = []
    partly = [m for m in maps if m not in replaced and set(held_values[m]) & set(write)]
    if partly:  # no file has one: a mapping of several values
        write = [v for v in write if not any(v in held_values[m] for m in partly)]
        notes.append(f"Left as they are, with the {name}s they map, since they map other {name}s too: "
                     + "; ".join(f"{label(m)} ({name} {', '.join(held_values[m])})" for m in partly) + ".")

    namers = _namers(doc, g)
    r.named_before = {d: [doc.get(d, "nrDrbDN"), *(doc.get(d, x) for x in PROFILES)] for d in maps
                      + doc.children(g, "NRDRB")}
    r.gone = set(replaced)
    whole = values is None
    drbs = [d for d in doc.children(g, "NRDRB") if instance(d) != DEFAULT_BEARER
            and namers[d] <= r.gone and (namers[d] or whole)]
    r.gone |= set(drbs)
    parts = [d for cls in PROFILES.values() for d in doc.children(g, cls)
             if namers[d] <= r.gone and (namers[d] or whole)]
    r.gone |= set(parts)

    # The mappings to write: (value, k-th of it, template, the mapping it replaces).
    old_of = defaultdict(list)
    for m in replaced:
        if len(held_values[m]) == 1:
            old_of[held_values[m][0]].append(m)
    jobs = []
    for v in write:
        olds = sorted(old_of.get(v, []), key=lambda m: (instance(m) != v, instance(m) != str(REPEAT + int(v)),
                                                        natural(m)))
        t = built.get(v)
        for k in range(max(1, len(olds))):
            old = olds[k] if k < len(olds) else None
            if t:
                variants = t.get("variants") or []
                content = t if k == 0 else variants[k - 1] if k - 1 < len(variants) else t
                source = (f"production's {name} {v} template" + (" for its second mapping" if 0 < k <= len(variants)
                                                                  else "")
                          + f" ({content['gnbs']} of the {t['of']} production gNBs the templates were built from)")
            else:
                b = bearer_of(ctx.site.by_dn, g, _full(g, doc.get(old, "nrDrbDN"))) if old else None
                if not b:
                    notes.append(f"{name} {v} has no production template and {label(old) if old else 'no mapping'}'s "
                                 "bearer can't be read: not written.")
                    continue
                content = {"p": {x: y for x, y in _el_values(doc, old)["p"].items() if x != "nrDrbDN"}, "bearer": b}
                source = f"its own settings ({label(old)}; production maps no {name} {v})"
            jobs.append({"v": v, "k": k, "content": content, "old": old, "source": source})

    # Numbers: production's first, then the lowest free for the rest.
    def preferred(job, cls):
        v, k = int(job["v"]), job["k"]
        if cls == r.cls:
            n = v if k == 0 else REPEAT + v if k == 1 and side == SA and 1 <= v <= 9 else None
            return n if n and (n != 1 or v == 1) else None
        if side == SA:
            return BEARER + v if k == 0 and 1 <= v <= 9 else job["map_n"] if k == 1 and job["map_n"] == REPEAT + v \
                else None
        return v if k == 0 and v >= 2 else None

    for cls, start, key in ((r.cls, 2, "map_n"), ("NRDRB", 20, "drb_n")):
        held = r.held(cls)  # the mappings' numbers first: a second mapping's bearer takes its mapping's
        for job in jobs:
            n = preferred(job, cls)
            job[key] = n if n is not None and n not in held else None
            if job[key]:
                held.add(job[key])
        for job in jobs:
            if job[key] is None:
                while start in held:
                    start += 1
                job[key] = start
                held.add(start)

    # Profiles on their production numbers first, so a fallback doesn't take one of them.
    for fallback in (False, True):
        for job in jobs:
            refs = job.setdefault("refs", {})
            for param, part in sorted(job["content"]["bearer"]["parts"].items()):
                if refs.get(param) is None:
                    refs[param] = r.part(part["cls"], part, job["v"], fallback)
    written = []
    for job in jobs:
        v, content, refs = job["v"], job["content"], job["refs"]
        own = job["drb_n"] == preferred(job, "NRDRB")
        drb = r.want("NRDRB", job["drb_n"], r.nr.filtered("NRDRB", content["bearer"]["drb"]), refs,
                     f"The bearer of {name} {v}, with the settings of {job['source']}"
                     + (f"; production numbers it {job['drb_n']}." if own else "."), own)
        rows = doc.items(job["old"], "snssaiList") if job["old"] else [{"snssaiDN": s} for s in slices]
        p = {x: y for x, y in (content.get("p") or {}).items() if r.nr.known(r.cls, x)}
        dn = f"{g}/{r.cls}-{job['map_n']}"
        r.desired[dn] = {"cls": r.cls, "content": {"p": p, "simple": {r.list: [v]},
                                                   "rows": {"snssaiList": rows} if side == SA else {}},
                         "refs": {"nrDrbDN": drb}, "own": job["map_n"] == preferred(job, r.cls),
                         "why": f"Maps {name} {v} to {label(drb)}, as {job['source']}"
                                + (f"; production numbers the mapping {job['map_n']}" if job["map_n"] ==
                                   preferred(job, r.cls) else "")
                                + (f"; for the slices {label(job['old'])} named" if rows and job["old"] else
                                   f"; for {_labels(s['snssaiDN'] for s in rows)}" if rows else "") + "."}
        written.append(dn)

    kept: dict[str, list[str]] = {}
    for cls in (*PROFILES.values(), "NRDRB", r.cls):
        for dn, x in sorted(r.desired.items(), key=lambda kv: natural(kv[0])):
            if x["cls"] != cls:
                continue
            took = f" It takes over {label(dn)}, which " + ("nothing used." if not namers[dn] else
                                                             "only what this replaces used.")
            w = why("qos", x["why"] + (took if dn in r.gone and not x["own"] else ""), "donor")
            if doc.exists(dn):
                kept[dn] = r.converge(dn, x, w)
            else:
                r.create(dn, x, w)
    removed = []
    for dn in [*replaced, *drbs, *parts]:
        if dn in r.desired or not doc.exists(dn):
            continue
        what = (f"Replaced by the {name} mappings written as production numbers them ({name} "
                f"{', '.join(held_values[dn]) or 'none'} here)" if dn in replaced else
                "Only the replaced mappings used it" if namers[dn] else "Nothing uses it")
        doc.delete(dn, why("qos", what + ".", "choice"))
        removed.append(dn)

    if removed:
        notes.append(f"Removed {len(removed)}: {_labels(removed)}.")
    gone_values = [v for v in extras if v not in write]
    if gone_values:
        one = len(gone_values) == 1
        notes.append(f"{name} {', '.join(gone_values)} {'was' if one else 'were'} mapped here, and no production gNB "
                     f"maps {'it' if one else 'them'}: removed. Pick {'it' if one else 'them'} under Keep to "
                     f"keep {'it' if one else 'them'} with {'its' if one else 'their'} own settings.")
    # What the replaced objects named that stays, since something else names it too.
    named = {_full(g, v) for d in [*replaced, *drbs] for v in r.named_before.get(d, ())}
    stay = sorted(d for d in named if d and d not in r.gone and _cls(d) in ("NRDRB", *PROFILES.values()))
    if stay:
        notes.append(f"Kept, since something else uses them: {_labels(stay)}"
                     + (" (NRDRB-1 is the default bearer)" if any(instance(d) == DEFAULT_BEARER and
                                                                  d.endswith("/NRDRB-1") for d in stay) else "")
                     + ".")
    left = {dn: k for dn, k in kept.items() if k}
    if left:
        notes.append("Kept settings production's templates don't have, since this release isn't the templates' "
                     "(" + TEMPLATE_RELEASE + "): " + "; ".join(f"{label(d)} {', '.join(k)}" for d, k in
                                                                sorted(left.items())) + ".")
    if r.nr.reused:
        notes.append(f"Reused {', '.join(sorted(set(r.nr.reused), key=natural))}: kept profiles with the template's "
                     "values.")
    notes += r.nr.notes
    return {"notes": list(dict.fromkeys(notes)), "written": written, "removed": removed, "values": [j["v"] for j in jobs]}
