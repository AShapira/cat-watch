import shutil

from catwatch.retention import Retention
from catwatch.store import Store


def segment(store,index,start,size=20_000_000):
    media=store.root/"media"
    media.mkdir(exist_ok=True)
    name=f"media/{'a'*32}-{index:06d}.mp4"
    with (store.root/name).open('wb') as f:
        f.truncate(size)
    store.add_segment(name,start,start+5,size)
    return store.segments()[-1]


def test_quota_expires_oldest_and_preserves_active_and_unrelated(tmp_path):
    root=tmp_path/"cat-watch"
    store=Store(root)
    store.configure({"storage_cap_gb":.05})
    outside=tmp_path/"foundation-sample.mp4"
    outside.write_bytes(b'leave me')
    older=segment(store,0,100)
    recent=segment(store,1,195)
    eid=store.open_visit("eating_pad",100,200)
    store.close_visit(eid,200,False)
    retain=Retention(store,reserve_bytes=15_000_000,disk_floor=0)
    assert retain.maintain(now=200)
    assert not (root/older["path"]).exists()
    assert (root/recent["path"]).exists()
    assert outside.read_bytes()==b'leave me'
    assert len(store.events())==1
    assert retain.last["used_bytes"]+retain.reserve<=50_000_000


def test_playing_evidence_protected_and_low_disk_pauses(tmp_path,monkeypatch):
    store=Store(tmp_path)
    s=segment(store,0,100,100)
    retain=Retention(store)
    retain.leases[s["id"]]=1
    assert not retain.delete(s)
    monkeypatch.setattr(shutil,'disk_usage',lambda p:shutil._ntuple_diskusage(100,99,1))
    assert not retain.maintain(now=200)
    assert (tmp_path/s["path"]).exists()


def test_non_media_bytes_count_and_unowned_paths_never_deleted(tmp_path):
    store=Store(tmp_path)
    (tmp_path/'other.mp4').write_bytes(b'private')
    store.add_segment('other.mp4',1,2,7)
    retain=Retention(store)
    import pytest
    with pytest.raises(ValueError):
        retain.delete(store.segments()[0])
    assert (tmp_path/'other.mp4').read_bytes()==b'private'
    assert retain.usage()>7


def test_usage_skips_learning_and_symlinks(tmp_path):
    store = Store(tmp_path/'owned')
    retain = Retention(store)
    before = retain.usage()
    (store.root/'learning').mkdir()
    (store.root/'learning'/'model.bin').write_bytes(b'x'*10000)
    outside = tmp_path/'outside'
    outside.mkdir()
    (outside/'private.bin').write_bytes(b'x'*10000)
    (store.root/'linked').symlink_to(outside, target_is_directory=True)
    (store.root/'nested').mkdir()
    (store.root/'nested'/'counted.bin').write_bytes(b'1234567')
    assert retain.usage() == before+7


def test_storage_scan_does_not_block_dashboard_database_reads(tmp_path, monkeypatch):
    import threading
    store = Store(tmp_path)
    retain = Retention(store)
    read_finished = threading.Event()
    readers = []
    def slow_scan():
        def read():
            store.config()
            read_finished.set()
        reader = threading.Thread(target=read, daemon=True)
        readers.append(reader)
        reader.start()
        assert read_finished.wait(1), 'Filesystem accounting held the database lock'
        return 0
    monkeypatch.setattr(retain, 'usage', slow_scan)
    try:
        assert retain.maintain()
    finally:
        for reader in readers:
            reader.join(timeout=2)


def test_missing_segment_does_not_create_fictitious_quota_space(tmp_path):
    store = Store(tmp_path)
    store.configure({'storage_cap_gb': .05})
    missing = segment(store, 0, 100, 20_000_000)
    (store.root/missing['path']).unlink()
    with (store.root/'unrelated.bin').open('wb') as stream:
        stream.truncate(40_000_000)
    retain = Retention(store, reserve_bytes=15_000_000, disk_floor=0)
    assert not retain.maintain(now=200)
    assert retain.last['used_bytes'] >= 40_000_000
