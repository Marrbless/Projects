from __future__ import annotations

"""Configuration dataclass for world generation."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class WorldSettings:
    seed: int = 0
    width: int = 50
    height: int = 50
    weather_patterns: Dict[str, float] = field(
        default_factory=lambda: {"rain": 0.3, "dry": 0.5, "snow": 0.2}
    )
    moisture: float = 0.5
    elevation: float = 0.5
    temperature: float = 0.5
    rainfall_intensity: float = 0.5
    disaster_intensity: float = 0.0
    seasonal_amplitude: float = 0.0
    sea_level: float = 0.3
    plate_activity: float = 0.5
    base_height: float = 0.5
    wind_strength: float = 0.5
    wind_dir: int = 1  # 0=N,1=E,2=S,3=W
    lapse_rate: float = 0.3
    # Threshold above which mountains dramatically reduce moisture transport
    orographic_threshold: float = 0.6
    # Factor controlling how much moisture is lost when crossing that threshold
    orographic_factor: float = 0.3
    # Minimum accumulated flow volume required for a tile to be considered a river source
    river_threshold: float = 0.1
    world_changes: bool = True
    mountain_elev: float = 0.8
    hill_elev: float = 0.6
    tundra_temp: float = 0.25
    desert_rain: float = 0.2
    fantasy_level: float = 0.0
    infinite: bool = False
    river_branch_threshold: float = 0.3
    river_branch_chance: float = 0.05
    lake_overflow_fraction: float = 1.5
    persistent_lake_fraction: float = 1.7


__all__ = ["WorldSettings"]
