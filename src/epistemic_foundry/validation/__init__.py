"""Validation Bay work packages that live on the ``src`` package tree.

The sealed cascade and replication surfaces are declared under
``validation_bay``; this package holds the higher-order validation *gates* that
compose them.  It carries no vocabulary of its own — every canonical enum value
its members reason about is read from the schema that declares it.
"""

from __future__ import annotations
