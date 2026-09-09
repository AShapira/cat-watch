"""Pure visit state and reporting logic; no camera or model dependencies."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

AREAS = ("eating_pad", "water_fountain", "litter_box")
BEHAVIORS = ("unknown", "eating_observed", "drinking_observed", "litter_box_behavior_observed", "visit_only")


def contains(polygon, point):
    x, y = point
    inside = False
    for i, (ax, ay) in enumerate(polygon):
        bx, by = polygon[i - 1]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def assign_area(polygons, point):
    matches = [name for name, polygon in polygons.items() if contains(polygon, point)]
    return matches[0] if len(matches) == 1 else None


@dataclass
class Presence:
    first: float
    last: float
    event_id: int | None = None


class VisitTracker:
    def __init__(self, store, enter=2.0, leave=5.0):
        self.store, self.enter, self.leave = store, enter, leave
        self.states = {}

    def observe(self, stamp, area):
        for name, state in list(self.states.items()):
            if name != area and stamp - state.last >= self.leave:
                if state.event_id is not None:
                    self.store.close_visit(state.event_id, state.last, False)
                del self.states[name]
        if area is None:
            return
        state = self.states.get(area)
        if state is None:
            state = self.states[area] = Presence(stamp, stamp)
        elif state.event_id is None and stamp - state.last > 1.5:
            state.first = stamp
        state.last = stamp
        if state.event_id is None and stamp - state.first >= self.enter:
            state.event_id = self.store.open_visit(area, state.first, stamp)
        elif state.event_id is not None:
            self.store.touch_visit(state.event_id, stamp)

    def interrupt(self):
        for state in self.states.values():
            if state.event_id is not None:
                self.store.close_visit(state.event_id, state.last, True)
        self.states.clear()


def report(events, coverage, start, end, timezone="Asia/Jerusalem"):
    tz = ZoneInfo(timezone)
    day = datetime.fromtimestamp(start, tz).date()
    rows = []
    while datetime.combine(day, time(), tz).timestamp() < end:
        a = max(start, datetime.combine(day, time(), tz).timestamp())
        b = min(end, datetime.combine(day + timedelta(days=1), time(), tz).timestamp())
        for area in AREAS:
            selected = [e for e in events if e["area"] == area and not e["rejected"]]
            behaviors = {label: sum(a <= e["start"] < b and e["behavior"] == label for e in selected)
                         for label in BEHAVIORS if label != "unknown"}
            rows.append({"date": str(day), "area": area,
                         "visits": sum(a <= e["start"] < b for e in selected),
                         "duration_seconds": round(sum(max(0, min(b, e["end"]) - max(a, e["start"])) for e in selected), 2),
                         "reviewed_visits": sum(a <= e["start"] < b and e["reviewed"] for e in selected),
                         "interrupted_visits": sum(a <= e["start"] < b and e["interrupted"] for e in selected),
                         "observed_seconds": round(sum(max(0, min(b, c["end"]) - max(a, c["start"])) for c in coverage), 2),
                         "period_seconds": b - a, "behaviors": behaviors})
        day += timedelta(days=1)
    return rows
