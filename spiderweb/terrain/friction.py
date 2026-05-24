from __future__ import annotations


def slope_cost(slope_degrees: float, multiplier: float = 2.0) -> float:
    """Return a terrain cost factor from slope angle.

    Cost starts at 1.0 and increases linearly with slope.
    """
    slope = max(0.0, float(slope_degrees))
    return 1.0 + (slope / 45.0) * multiplier


def ridge_cost(is_ridge_crossing: bool, penalty: float = 1.5) -> float:
    """Return additive friction multiplier for ridge crossings."""
    return float(penalty) if is_ridge_crossing else 1.0


def karst_cost(is_karst: bool, penalty: float = 1.25) -> float:
    """Return additive friction multiplier for karst instability zones."""
    return float(penalty) if is_karst else 1.0


def combined_friction(
    slope_degrees: float = 0.0,
    is_ridge_crossing: bool = False,
    is_karst: bool = False,
) -> float:
    return (
        slope_cost(slope_degrees)
        * ridge_cost(is_ridge_crossing)
        * karst_cost(is_karst)
    )
