"""
The actions the bar offers, in the order it lists them. See __init__.py
for what an action module provides.
"""
from __future__ import annotations

from . import (Context, add_radio, ca_action, carrier, core, delete, drx, endc, endc_gnb, ip_address, ip_interface, lte_cell,
               neighbour_enb, neighbour_gnb, nr_cell, ntp_dns, plmn, product_code, qos, remove_module, renumber, slice,
               static_route, tidy, voice)

ACTIONS = {a.ID: a for a in (nr_cell, lte_cell, ca_action, drx, endc, qos, voice, slice, carrier, neighbour_enb, endc_gnb,
                                  neighbour_gnb, core, plmn, ip_address, ip_interface, static_route, ntp_dns, add_radio, remove_module, product_code, renumber, tidy, delete)}


def catalog(ctx: Context) -> list[dict]:
    """Every action with whether it can run on this file, for the bar."""
    out = []
    for a in ACTIONS.values():
        try:
            reason = a.available(ctx)
        except Exception as e:  # an unreadable corner of the file shouldn't hide the bar
            reason = f"Couldn't read this file: {e}"
        out.append({"id": a.ID, "title": a.TITLE, "group": a.GROUP, "summary": a.SUMMARY, "ui": a.UI,
                    "keywords": getattr(a, "KEYWORDS", ""), "available": reason is None, "reason": reason})
    return out
