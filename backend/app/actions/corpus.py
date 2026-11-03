"""
What main.py's corpus index keeps per file (cached by mtime): the CA
wizard's profile (parameters each class sets per release, for the release
filter, and the CA donor summary), the hardware evidence, and the file's
eNBs and gNBs as a neighbour sees them (sites.summary), its QoS profiles
(qos_files.summary) and a carrier object of each kind (carrier_files).

Pure: bytes in, dict out.
"""
from __future__ import annotations

from ..ca import _load
from ..ca_wizard import profile_loaded
from .carrier_files import evidence as carriers
from .hardware import evidence
from .qos_files import summary as qos
from .sites import summary


def profile(raw: bytes) -> dict:
    mos = _load(raw)
    return {**profile_loaded(mos), "hardware": evidence(mos), "sites": summary(mos), "qos": qos(mos),
            "carriers": carriers(mos)}
