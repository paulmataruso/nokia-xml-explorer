"""
What the carrier action reads from each file of the corpus: one object of
each carrier class (and REDRT per RAT) as values, for files that lack one
to copy (carrier.py). Values only; the action replaces the carrier.

Pure: works on ca._load() output.
"""
from __future__ import annotations

CLASSES = ("IRFIM", "LNHOIF", "NRFIM", "REDRT", "NRIRFIM", "NRLIM", "NRREDRT")


def kind_of(m: dict) -> str:
    """The template key of a carrier object: its class, and for REDRT the
    RAT it redirects to ("REDRT:nr")."""
    return f"REDRT:{m['p'].get('redirRat')}" if m["cls"] == "REDRT" else m["cls"]


def evidence(mos: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for m in mos:
        if m["cls"] in CLASSES:
            out.setdefault(kind_of(m), {"p": dict(m["p"]), "lists": {k: [dict(r) for r in v] for k, v in m["lists"].items()
                                                                       if k not in m["simple"]},
                                        "version": m["version"], "inst": m["dn"].rsplit("-", 1)[-1]})
    return out
