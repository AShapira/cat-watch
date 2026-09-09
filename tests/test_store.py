import pytest

from catwatch.store import Store


@pytest.fixture
def store(tmp_path):
    store=Store(tmp_path)
    (tmp_path/"media").mkdir()
    path="media/"+"a"*32+"-000000.mp4"
    (tmp_path/path).write_bytes(b"evidence")
    store.add_segment(path,80,150,8)
    return store


def event(store,start=100,end=110):
    eid=store.open_visit("eating_pad",start,end)
    store.close_visit(eid,end,False)
    return eid


def test_corrections_preserve_observations(store):
    eid=event(store)
    changed=store.correct(eid,{"end":112,"behavior":"eating_observed"})
    assert changed["original"]["end"]==110
    assert changed["original"]["behavior"]=="unknown"
    assert changed["end"]==112 and changed["reviewed"]
    assert len(changed["history"])==1
    with pytest.raises(ValueError):
        store.correct(eid,{"behavior":"drinking_observed"})


def test_merge_split_do_not_double_count(store):
    a,b=event(store),event(store,112,120)
    merged=store.merge([a,b])
    accepted=lambda:[e for e in store.events() if not e["rejected"]]
    assert len(accepted())==1
    assert merged["start"]==100 and merged["end"]==120
    parts=store.split(merged["id"],109)
    assert len(accepted())==2
    assert sum(e["end"]-e["start"] for e in parts)==20
    assert all(e["reviewed"] for e in parts)


def test_compound_edit_rolls_back(store):
    eid=event(store)
    # Simulate a failure after the first child was inserted.
    original=store.add_manual
    calls=0
    def fail(changes,action="add"):
        nonlocal calls
        calls+=1
        if calls==2:
            raise ValueError("test failure")
        return original(changes,action)
    store.add_manual=fail
    with pytest.raises(ValueError):
        store.split(eid,105)
    assert len(store.events())==1
    assert not store.event(eid)["rejected"]


def test_open_and_evidence_rules(store):
    eid=store.open_visit("litter_box",100,110)
    with pytest.raises(ValueError):
        store.correct(eid,{"rejected":True})
    with pytest.raises(ValueError):
        store.add_manual({"area":"litter_box","start":1000,"end":1020})
    with pytest.raises(ValueError):
        store.add_manual({"area":"litter_box","start":float('nan'),"end":1020})


def test_config_rejects_partial_and_invalid_areas(store):
    with pytest.raises(ValueError):
        store.configure({"polygons":{"eating_pad":[[0,0],[1,0],[1,1]]}})
    with pytest.raises(ValueError):
        store.configure({"storage_cap_gb":float('nan')})
    assert store.config()["storage_cap_gb"]==50
