"""Download safety and provenance; no network or fabricated QC results."""
import hashlib
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'prepare_test_data', Path(__file__).resolve().parents[2] / 'scripts/prepare-test-data.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


@pytest.fixture
def source():
    data = b'@read/1\nACGT\n+\nIIII\n'
    return data, {'repository': 'example/fixtures', 'commit': 'a' * 40, 'files': [
        {'name': 'reads.fastq', 'path': 'data/reads.fastq', 'size': len(data),
         'sha256': hashlib.sha256(data).hexdigest()}]}


def test_download_preserves_bytes_and_pinned_provenance(tmp_path, monkeypatch, source):
    data, inventory = source
    calls = []

    def fetch(url, limit):
        calls.append((url, limit))
        return data if url.endswith('/reads.fastq') else b'upstream notice\n'

    monkeypatch.setattr(prepare, 'fetch', fetch)
    rows = prepare.public_files(tmp_path, 'fixture', inventory, True, 'upstream-synthetic')
    assert (tmp_path / 'fixture/reads.fastq').read_bytes() == data
    assert (tmp_path / 'fixture/UPSTREAM-LICENSE').read_bytes() == b'upstream notice\n'
    assert rows[0]['kind'] == 'upstream-synthetic'
    assert rows[0]['commit'] == inventory['commit']
    assert rows[0]['path'] == 'fixture/reads.fastq'
    assert inventory['commit'] in rows[0]['url']
    calls.clear()
    assert prepare.public_files(tmp_path, 'fixture', inventory, True, 'upstream-synthetic') == rows
    assert not calls


@pytest.mark.parametrize('bad', [b'truncated', b'@read/1\nTGCA\n+\nIIII\n'])
def test_bad_download_is_not_saved(tmp_path, monkeypatch, source, bad):
    _, inventory = source
    monkeypatch.setattr(prepare, 'fetch', lambda *_: bad)
    with pytest.raises(ValueError, match='checksum mismatch'):
        prepare.public_files(tmp_path, 'fixture', inventory, True)
    assert not (tmp_path / 'fixture/reads.fastq').exists()


def test_existing_files_rechecked_without_download_or_overwrite(tmp_path, monkeypatch, source):
    data, inventory = source
    monkeypatch.setattr(prepare, 'fetch', lambda *_: pytest.fail('unexpected download'))
    assert prepare.public_files(tmp_path, 'fixture', inventory, False) == []
    target = tmp_path / 'fixture/reads.fastq'
    prepare.save(target, data)
    assert len(prepare.public_files(tmp_path, 'fixture', inventory, False)) == 1
    target.write_bytes(b'locally changed')
    with pytest.raises(ValueError, match='checksum mismatch'):
        prepare.public_files(tmp_path, 'fixture', inventory, True)
    assert target.read_bytes() == b'locally changed'


def test_symlink_rejected_before_fetch(tmp_path, monkeypatch, source):
    data, inventory = source
    original = tmp_path / 'original.fastq'
    original.write_bytes(data)
    target = tmp_path / 'fixture/reads.fastq'
    target.parent.mkdir()
    target.symlink_to(original)
    monkeypatch.setattr(prepare, 'fetch', lambda *_: pytest.fail('unexpected download'))
    with pytest.raises(ValueError, match='symlink'):
        prepare.public_files(tmp_path, 'fixture', inventory, True)
    assert original.read_bytes() == data
