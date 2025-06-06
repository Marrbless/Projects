from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from world.world import WorldSettings, World, perlin_noise


@dataclass
class SettlementState:
    """Simple container tracking the state of a settlement."""

    resources: int = 100
    population: int = 100
    buildings: int = 10
    defenses: int = 0
    location: Tuple[int, int] | None = None


class Event:
    """Base class for random world events."""

    name: str = "event"

    def severity(self, state: SettlementState, world: World) -> float:
        """Return a location-based severity influenced by disaster intensity."""
        if not state.location:
            base = 1.0
        else:
            x, y = state.location
            n = perlin_noise(x, y, world.settings.seed, scale=0.1)
            base = 0.3 + n * 3.0
            rnd = random.Random((x << 16) ^ (y << 8) ^ world.settings.seed).random() - 0.5
            base *= 1 + rnd * 0.2
        return base * (1 + world.settings.disaster_intensity)

    def apply(self, state: SettlementState, world: World) -> None:
        raise NotImplementedError


class Flood(Event):
    name = "flood"

    def apply(self, state: SettlementState, world: World) -> None:
        sev = self.severity(state, world)
        # Damage buildings. Defenses mitigate some damage.
        rnd = random.Random((state.location[0] if state.location else 0) * 17 + (state.location[1] if state.location else 0) * 23 + world.settings.seed)
        loss = max(0, int(round(0.3 * state.buildings * sev)) - state.defenses + rnd.randint(0, 1))
        state.buildings = max(0, state.buildings - loss)
        # Resources lost proportional to building loss
        res_loss = min(state.resources, int(round(loss * 2 * sev)))
        state.resources -= res_loss
        if state.location and world.settings.world_changes:
            hex_ = world.get(*state.location)
            if hex_:
                hex_.flooded = True
                if sev > 1.3:
                    if hex_.river:
                        # convert rivers into lakes when flooding is severe
                        hex_.river = False
                        world.rivers = [
                            seg
                            for seg in world.rivers
                            if seg.start != hex_.coord and seg.end != hex_.coord
                        ]
                        if hex_.coord not in world.lakes:
                            world.lakes.append(hex_.coord)
                        hex_.lake = True
                        hex_.terrain = "water"
                    if hex_.terrain == "hills":
                        # severe flooding can reshape hills into mountains
                        hex_.terrain = "mountains"
                    else:
                        hex_.terrain = "water"
                        hex_.lake = True


class Drought(Event):
    name = "drought"

    def apply(self, state: SettlementState, world: World) -> None:
        sev = self.severity(state, world)
        res_loss = int(0.2 * state.resources * sev)
        state.resources = max(0, state.resources - res_loss)
        pop_loss = int(0.1 * state.population * sev)
        state.population = max(0, state.population - pop_loss)
        if state.location and world.settings.world_changes:
            hex_ = world.get(*state.location)
            if hex_:
                hex_.moisture = max(0.0, hex_.moisture - 0.1 * sev)
                if sev > 1.3:
                    if hex_.lake:
                        # severe drought dries up lakes completely
                        hex_.lake = False
                        hex_.terrain = "plains"
                        world.lakes = [c for c in world.lakes if c != hex_.coord]
                    else:
                        hex_.terrain = "desert"


class Raid(Event):
    name = "raid"

    def apply(self, state: SettlementState, world: World) -> None:
        sev = self.severity(state, world)
        # Defenses reduce impact
        effective = max(1, int((5 - state.defenses) * sev))
        res_loss = min(state.resources, effective * 3)
        bld_loss = max(0, effective - 1)
        state.resources -= res_loss
        state.buildings = max(0, state.buildings - bld_loss)
        if state.location and world.settings.world_changes:
            hex_ = world.get(*state.location)
            if hex_:
                hex_.ruined = True
                if sev > 1.3:
                    state.buildings = 0
                    if hex_.terrain == "hills":
                        # extreme raids can reshape the land into mountains
                        hex_.terrain = "mountains"


class Earthquake(Event):
    name = "earthquake"

    def apply(self, state: SettlementState, world: World) -> None:
        sev = self.severity(state, world)
        bld_loss = int(0.4 * state.buildings * sev)
        pop_loss = int(0.2 * state.population * sev)
        state.buildings = max(0, state.buildings - bld_loss)
        state.population = max(0, state.population - pop_loss)
        if state.location and world.settings.world_changes:
            hex_ = world.get(*state.location)
            if hex_ and sev > 1.3:
                # severe quakes raise the land into mountains
                hex_.terrain = "mountains"


class Hurricane(Event):
    name = "hurricane"

    def apply(self, state: SettlementState, world: World) -> None:
        sev = self.severity(state, world)
        loss = max(0, int(0.3 * state.buildings * sev) - state.defenses)
        state.buildings = max(0, state.buildings - loss)
        res_loss = min(state.resources, int(state.resources * 0.3 * sev))
        state.resources -= res_loss
        if state.location and world.settings.world_changes:
            hex_ = world.get(*state.location)
            if hex_:
                hex_.flooded = True
                if sev > 1.3:
                    if hex_.river:
                        # intense storms can swell rivers into lakes
                        hex_.river = False
                        world.rivers = [
                            seg
                            for seg in world.rivers
                            if seg.start != hex_.coord and seg.end != hex_.coord
                        ]
                        if hex_.coord not in world.lakes:
                            world.lakes.append(hex_.coord)
                    hex_.terrain = "water"
                    hex_.lake = True


ALL_EVENTS: List[type[Event]] = [Flood, Drought, Raid, Earthquake, Hurricane]


class EventSystem:
    """Schedules and triggers events based on world settings."""

    def __init__(
        self,
        settings: WorldSettings,
        rng: Optional[random.Random] = None,
        event_weights: Optional[dict[str, float]] = None,
    ) -> None:
        self.settings = settings
        self.rng = rng or random.Random()
        self.event_weights = event_weights or {
            "flood": 1.0,
            "drought": 1.0,
            "raid": 1.0,
            "earthquake": 1.0,
            "hurricane": 1.0,
        }
        self.turn_counter = 0
        self.next_event_turn = self._schedule_next()

    def _schedule_next(self) -> int:
        """Return the turn number for the next event."""
        # Larger base delay scaled by disaster intensity. Low intensity means
        # delays are much longer while high intensity keeps them short.
        min_base = 10 + int((1 - self.settings.disaster_intensity) * 20)
        max_base = 20 + int((1 - self.settings.disaster_intensity) * 40)
        base = self.rng.randint(min_base, max_base)

        weather_factor = 1.0 + self.settings.moisture * 0.5
        delay = max(2, int(base * weather_factor))
        return self.turn_counter + delay

    def _choose_event(self) -> Event:
        flood_base = self.event_weights.get("flood", 1.0)
        drought_base = self.event_weights.get("drought", 1.0)
        raid_base = self.event_weights.get("raid", 1.0)
        earthquake_base = self.event_weights.get("earthquake", 1.0)
        hurricane_base = self.event_weights.get("hurricane", 1.0)

        flood_w = flood_base * self.settings.weather_patterns.get("rain", 0.1) * self.settings.moisture
        drought_w = drought_base * self.settings.weather_patterns.get("dry", 0.1) * (1 - self.settings.moisture)
        raid_w = raid_base
        earthquake_w = earthquake_base * self.settings.plate_activity
        hurricane_w = hurricane_base * self.settings.weather_patterns.get("rain", 0.1) * self.settings.moisture

        weights = [flood_w, drought_w, raid_w, earthquake_w, hurricane_w]
        event_cls = self.rng.choices(ALL_EVENTS, weights=weights, k=1)[0]
        return event_cls()

    def advance_turn(self, state: SettlementState, world: World) -> Optional[Event]:
        """Advance the internal clock and trigger events when scheduled."""

        self.turn_counter += 1
        if self.turn_counter >= self.next_event_turn:
            event = self._choose_event()
            event.apply(state, world)
            self.next_event_turn = self._schedule_next()
            return event
        return None

