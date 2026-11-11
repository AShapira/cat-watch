import time

from catwatch.store import Store


def test_protected_archive_cleanup_bounds_scan_and_reaches_later_expired_rows(tmp_path, monkeypatch):
    store = Store(tmp_path)
    old = time.time()-8*86400
    with store.db() as db:
        db.execute('INSERT INTO protected_sessions VALUES (1)')
        db.executemany('INSERT INTO observations(session_id,stamp,kind,body) VALUES (?,?,?,?)',
                       [(1, old, 'detection', '{}')]*2500 +
                       [(None, old, 'detection', '{}'), (2, old, 'detection', '{}'),
                        (2, time.time(), 'detection', '{}')])
    clock = [100.]
    monkeypatch.setattr('catwatch.investigation.time.monotonic', lambda: clock[0])
    store.observation(time.time(), 'detection', {})
    assert store._observation_prune_cursor == 1000
    # A burst of detections must not repeatedly traverse protected history.
    for _ in range(10):
        store.observation(time.time(), 'detection', {})
    assert store._observation_prune_cursor == 1000
    clock[0] += 60
    store.observation(time.time(), 'detection', {})
    assert store._observation_prune_cursor == 2000
    clock[0] += 60
    store.observation(time.time(), 'detection', {})
    assert store._observation_prune_cursor == 0
    with store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM observations WHERE session_id=1').fetchone()[0] == 2500
        assert db.execute('SELECT COUNT(*) FROM observations WHERE stamp<? AND session_id IS NOT 1',
                          (time.time()-7*86400,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM observations WHERE session_id=2').fetchone()[0] == 1
