"""Foundry Console packages.

This marker exists so ``epistemic_foundry.console`` and the console packages
beneath it are discoverable by the same ``find_packages`` rule that ships the
rest of the runtime.  It declares no behaviour and holds no canonical
vocabulary; each console package under it projects an already-sealed surface
into read-only view records and confers no authority of its own.
"""

from __future__ import annotations
