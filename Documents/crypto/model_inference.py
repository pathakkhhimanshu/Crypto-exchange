from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class VolatilitySignal:
    value_bps: float


@dataclass(frozen=True)
class ZScoreSignal:
    value: float


def compute_volatility_bps(series: Sequence[float]) -> VolatilitySignal:
    values = np.asarray(series, dtype=np.float64)
    if values.size < 2:
        return VolatilitySignal(value_bps=0.0)
    returns = np.abs(np.diff(values) / np.maximum(values[:-1], 1e-9))
    return VolatilitySignal(value_bps=float(np.mean(returns) * 10_000))


def compute_zscore(series: Sequence[float]) -> ZScoreSignal:
    values = np.asarray(series, dtype=np.float64)
    if values.size < 2:
        return ZScoreSignal(value=0.0)
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std <= 0:
        return ZScoreSignal(value=0.0)
    return ZScoreSignal(value=float((values[-1] - mean) / std))
