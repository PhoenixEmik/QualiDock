from pathlib import Path
import os
import time

import pytest
from qualidock.files import FileAccess, DirectoryChanged


def populate(root, count=100):
    for index in range(count):
        (root/f'sample_{index:05d}_R1.fastq.gz').touch()
        (root/f'sample_{index:05d}_R2.fastq.gz').touch()


def test_warm_pages_reuse_name_index_and_only_stat_page_and_mates(tmp_path, monkeypatch):
    populate(tmp_path, 500)
    files = FileAccess([tmp_path])
    first = files.browse(str(tmp_path), limit=1)
    assert first['entries'][0]['paired']
    assert first['entries'][0]['mate'].endswith('_R2.fastq.gz')
    real = files._entry
    calls = []
    def counted(directory, name):
        calls.append(name)
        return real(directory, name)
    monkeypatch.setattr(files, '_entry', counted)
    monkeypatch.setattr('qualidock.files.os.scandir', lambda path: (_ for _ in ()).throw(AssertionError('A warm page rescanned the directory')))
    second = files.browse(str(tmp_path), offset=1, limit=10, snapshot=first['snapshot'])
    assert second['snapshot'] == first['snapshot'] and second['next_offset'] == 11
    assert len(calls) <= 20
    assert all(entry['paired'] for entry in second['entries'])


def test_changes_reject_stale_pagination_and_refresh_rebuilds(tmp_path):
    populate(tmp_path, 2)
    files = FileAccess([tmp_path])
    first = files.browse(str(tmp_path), limit=1)
    (tmp_path/'sample_00000.1.fq').touch()  # Makes R1 ambiguous.
    with pytest.raises(DirectoryChanged): files.browse(str(tmp_path), offset=1, snapshot=first['snapshot'])
    fresh = files.browse(str(tmp_path), refresh=True)
    assert fresh['snapshot'] != first['snapshot']
    assert not next(entry for entry in fresh['entries'] if entry['name']=='sample_00000_R2.fastq.gz')['paired']


def test_pairing_lanes_ambiguous_incomplete_and_invalid_links(tmp_path):
    for name in ['sample_L001_R1_001.fastq.gz', 'sample_L001_R2_001.fastq.gz', 'sample_L002_R1_001.fastq.gz', 'amb_R1.fastq', 'amb.1.fq', 'amb_R2.fastq']:
        (tmp_path/name).touch()
    outside = tmp_path.parent/'outside.fastq'; outside.touch()
    (tmp_path/'sample_L002_R2_001.fastq.gz').symlink_to(outside)
    files=FileAccess([tmp_path])
    result=files.browse(str(tmp_path))
    rows={entry['name']:entry for entry in result['entries']}
    assert rows['sample_L001_R1_001.fastq.gz']['paired']
    assert not rows['sample_L002_R1_001.fastq.gz']['paired']
    assert all(not row['paired'] for name,row in rows.items() if name.startswith('amb'))
    assert 'sample_L002_R2_001.fastq.gz' not in rows


def test_sparse_pages_advance_cursor_without_duplicate_rows(tmp_path, monkeypatch):
    populate(tmp_path, 2)
    files=FileAccess([tmp_path])
    first=files.browse(str(tmp_path), limit=1)
    real=files._entry
    monkeypatch.setattr(files, '_entry', lambda directory,name: None if '00000_R2' in name else real(directory,name))
    second=files.browse(str(tmp_path), offset=1, limit=1, snapshot=first['snapshot'])
    assert second['entries']==[] and second['next_offset']==2
    third=files.browse(str(tmp_path), offset=second['next_offset'], limit=1, snapshot=first['snapshot'])
    assert third['entries'][0]['name']=='sample_00001_R1.fastq.gz'


def test_cache_budget_expiry_and_force_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr('qualidock.files.MAX_INDEX_ENTRIES', 4)
    a=tmp_path/'a'; a.mkdir(); populate(a,2)
    b=tmp_path/'b'; b.mkdir(); populate(b,1)
    files=FileAccess([tmp_path])
    old=files.browse(str(a))
    files.browse(str(b))
    assert len(files._snapshots)==1
    with pytest.raises(DirectoryChanged): files.browse(str(a), snapshot=old['snapshot'])
    (a/'too-many.txt').touch()
    with pytest.raises(ValueError,match='exceeds'): files.browse(str(a))
    (a/'too-many.txt').unlink()
    fresh=files.browse(str(a)); files._snapshots[str(a)]['accessed']-=1000
    with pytest.raises(DirectoryChanged): files.browse(str(a),snapshot=fresh['snapshot'])


def test_filesystem_change_during_page_is_explicit(tmp_path, monkeypatch):
    populate(tmp_path,2)
    files=FileAccess([tmp_path]); files.browse(str(tmp_path))
    original=files._entry
    def changing(directory,name):
        value=original(directory,name)
        (directory/'new.txt').touch()
        return value
    monkeypatch.setattr(files,'_entry',changing)
    with pytest.raises(DirectoryChanged): files.browse(str(tmp_path))


def test_api_snapshot_and_refresh_status(client, setup):
    _,root=setup
    first=client.get('/api/files',params={'path':str(root),'limit':1}).json()
    (root/'new.fastq').touch()
    assert client.get('/api/files',params={'path':str(root),'offset':1,'snapshot':first['snapshot']}).status_code==409
    refreshed=client.get('/api/files',params={'path':str(root),'refresh':'true'}).json()
    assert refreshed['snapshot']!=first['snapshot']
    assert refreshed['next_offset'] is None
