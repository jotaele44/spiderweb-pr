"""DEM sources broken down by acquisition platform: catalog, registration accounting and merge policy."""

from .catalog import load_catalog, products_by_id
from .policy import evaluate_platform_mix, shared_acquisition_roots

__all__ = ["evaluate_platform_mix", "load_catalog", "products_by_id", "shared_acquisition_roots"]
