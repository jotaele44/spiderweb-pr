from __future__ import annotations

import numpy as np


class TerrainCostSurface:
    def __init__(
        self,
        slope_weight: float = 1.0,
        ridge_penalty: float = 2.0,
        karst_penalty: float = 1.5,
    ):
        self.slope_weight = slope_weight
        self.ridge_penalty = ridge_penalty
        self.karst_penalty = karst_penalty

    def build(
        self,
        slope_array,
        ridge_mask=None,
        karst_mask=None,
    ):
        cost = 1.0 + (np.nan_to_num(slope_array) / 45.0) * self.slope_weight

        if ridge_mask is not None:
            cost = np.where(ridge_mask, cost * self.ridge_penalty, cost)

        if karst_mask is not None:
            cost = np.where(karst_mask, cost * self.karst_penalty, cost)

        return cost.astype("float32")
