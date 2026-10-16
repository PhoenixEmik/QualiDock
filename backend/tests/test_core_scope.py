"""Intentional removals and lossless offline recovery, not administrative APIs."""
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import pytest
from test_workspace import start, wait

spec = importlib.util.spec_from_file_location('legacy_export', Path(__file__).resolve().parents[2]/'scripts/export-legacy-projects.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def test_no_catalog_dependency_or_administrative_routes(client, setup):
    settings, root = setup
    # Even an unreadable/unknown legacy format cannot prevent scientific work.
    catalog = settings.output/'projects.sqlite3'
    catalog.write_bytes(b'untouched obsolete catalog')
    original = catalog.read_bytes()
    for path in ('projects','batches','cohort/preview','screening'):
        assert client.get('/api/'+path).status_code==404
    run = wait(client,start(client, root, mode='fastqc')['id'])
    assert run['state']=='completed'
    for suffix in ('delivery','expected-template','release-policy','release-review/evaluate','screening'):
        assert client.get(f"/api/runs/{run['id']}/{suffix}").status_code==404
    assert catalog.read_bytes()==original


def test_export_is_lossless_readonly_and_exclusive(tmp_path):
    database=tmp_path/'projects.sqlite3'; (tmp_path/'.lock').touch(mode=0o600)
    with sqlite3.connect(database) as db:
        db.execute('PRAGMA user_version=3')
        db.execute('CREATE TABLE entities (id TEXT, fields TEXT)')
        db.execute('CREATE TABLE analysis_links (id TEXT, analysis_id TEXT, project_id TEXT)')
        db.execute('INSERT INTO entities VALUES (?,?)',('p',json.dumps({'display_name':'Historical project','notes':'科学'})))
        db.execute('INSERT INTO analysis_links VALUES (?,?,?)',('link','a'*32,'p'))
    database.chmod(0o600)
    before=database.read_bytes(); destination=tmp_path/'archive.json'
    value=legacy.export(database,destination)
    assert value==json.loads(destination.read_text())
    assert value['tables']['analysis_links'][0]['analysis_id']=='a'*32
    assert json.loads(value['tables']['entities'][0]['fields'])['notes']=='科学'
    assert value['catalog_sha256']==hashlib.sha256(before).hexdigest()
    assert database.read_bytes()==before
    with pytest.raises(FileExistsError): legacy.export(database,destination)
    alias=tmp_path/'alias.sqlite3'; alias.symlink_to(database)
    with pytest.raises(ValueError,match='symlink'): legacy.export(alias,tmp_path/'escaped.json')
    with (tmp_path/'.lock').open('r') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError): legacy.export(database,tmp_path/'locked.json')
    Path(str(database)+'-wal').touch()
    with pytest.raises(ValueError,match='sidecars'): legacy.export(database,tmp_path/'transaction.json')
    assert database.read_bytes()==before
