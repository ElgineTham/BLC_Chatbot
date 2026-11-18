"""Every name the menu knows, mapped to its display name (spec 022 section 3.1)."""

from __future__ import annotations

from blc.tools.bev_tools import Catalog


def menu_names(catalog: Catalog) -> dict[str, str]:
    """Normalised item names, aliases and package names mapped to their display names."""
    return {key: display for key, (_kind, display) in catalog._names.items()}
