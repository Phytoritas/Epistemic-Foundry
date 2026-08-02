"""Effect engines.

A package marker only (HD-EF4-E05-SCOPE-20260802-001): setuptools discovers
packages with ``find_packages``, which needs an ``__init__`` at every level, so
without this file ``effects.v4_e05`` would import from a source checkout but be
absent from the built wheel. It declares no vocabulary and no API.
"""
