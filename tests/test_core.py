from datetime import datetime
from zoneinfo import ZoneInfo

from catwatch.core import VisitTracker, assign_area, report
from catwatch.store import Store


def test_stationary_visit_and_exit_timeout(tmp_path):
    store=Store(tmp_path)
    tracker=VisitTracker(store)
    for n in range(21):
        tracker.observe(100+n*.5,"eating_pad")
    assert len(store.events())==1
    tracker.observe(114.5,None)
    assert store.events()[0]["open"]
    tracker.observe(115,None)
    event=store.events()[0]
    assert (event["start"],event["end"],event["behavior"],event["open"])==(100,110,"unknown",False)


def test_pass_by_jitter_and_transition(tmp_path):
    store=Store(tmp_path)
    tracker=VisitTracker(store)
    tracker.observe(100,"eating_pad")
    tracker.observe(100.5,"eating_pad")
    tracker.observe(106,None)
    assert not store.events()
    for n in range(7):
        tracker.observe(110+n*.5,"water_fountain")
    tracker.observe(115,None)
    tracker.observe(116,"water_fountain")
    assert len(store.events())==1
    for n in range(6):
        tracker.observe(117+n*.5,"litter_box")
    tracker.interrupt()
    events=store.events()
    assert len(events)==2
    assert all(e["interrupted"] for e in events)


def test_recovery_closes_at_last_observation(tmp_path):
    store=Store(tmp_path)
    store.open_visit("litter_box",10,15)
    Store(tmp_path).recover()
    assert store.events()[0]["end"]==15
    assert store.events()[0]["interrupted"]


def test_overlapping_polygons_are_ambiguous():
    square=[[0,0],[1,0],[1,1],[0,1]]
    assert assign_area({"eating_pad":square},(.5,.5))=="eating_pad"
    assert assign_area({"eating_pad":square,"litter_box":square},(.5,.5)) is None
    assert assign_area({"eating_pad":square},(2,2)) is None


def test_midnight_duration_count_and_dst():
    tz=ZoneInfo("Asia/Jerusalem")
    stamp=lambda value:datetime.fromisoformat(value).replace(tzinfo=tz).timestamp()
    start=stamp("2026-09-08T23:59:50")
    end=stamp("2026-09-09T00:00:20")
    event={"area":"eating_pad","start":start,"end":end,"rejected":False,"reviewed":False,"interrupted":False,"behavior":"unknown"}
    rows=report([event],[{"start":start,"end":end}],stamp("2026-09-08T00:00:00"),stamp("2026-09-10T00:00:00"))
    eating=[r for r in rows if r["area"]=="eating_pad"]
    assert [(r["visits"],r["duration_seconds"]) for r in eating]==[(1,10),(0,20)]
    # Israel's fall-back day has 25 elapsed hours.
    rows=report([],[],stamp("2026-10-25T00:00:00"),stamp("2026-10-26T00:00:00"))
    assert rows[0]["period_seconds"]==25*3600
