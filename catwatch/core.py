"""Pure visit state and reporting logic; no camera or model dependencies."""
from dataclasses import dataclass
import math
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

AREAS = ("eating_pad", "water_fountain", "litter_box")
BEHAVIORS = ("unknown", "eating_observed", "drinking_observed", "litter_box_behavior_observed", "visit_only")


def box_overlap(polygon, box):
    """Intersection / box area, clipping the polygon to the box's four edges."""
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        return 0.
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return 0.
    points = list(polygon)
    for axis, bound, sign in ((0,x1,1),(0,x2,-1),(1,y1,1),(1,y2,-1)):
        clipped = []
        for a, b in zip(points, points[1:]+points[:1]):
            inside_a = sign*(a[axis]-bound) >= 0
            inside_b = sign*(b[axis]-bound) >= 0
            if inside_a:
                clipped.append(a)
            if inside_a != inside_b:
                t = (bound-a[axis])/(b[axis]-a[axis])
                clipped.append([a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1])])
        points = clipped
    intersection = abs(sum(a[0]*b[1]-b[0]*a[1]
                           for a,b in zip(points,points[1:]+points[:1])))/2
    return max(0., min(1., intersection/((x2-x1)*(y2-y1))))


def box_assignment(polygons, box, thresholds):
    overlaps = {name:box_overlap(polygon,box) for name,polygon in polygons.items()}
    matches = [name for name,ratio in overlaps.items()
               if ratio > 0 and ratio+1e-12 >= thresholds[name]]
    return {'areas':matches, 'overlaps':overlaps,
            'location':'inside' if matches else 'outside' if polygons else 'unknown'}



@dataclass
class Presence:
    first: float
    last: float
    event_id: int | None = None


class VisitTracker:
    def __init__(self, store, enter=2.0, leave=5.0):
        self.store, self.enter, self.leave = store, enter, leave
        self.states = {}

    def observe(self, stamp, areas):
        areas = set(areas)
        for name, state in list(self.states.items()):
            if name not in areas and stamp - state.last >= self.leave:
                if state.event_id is not None:
                    self.store.close_visit(state.event_id, state.last, False)
                del self.states[name]
        for area in areas:
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
