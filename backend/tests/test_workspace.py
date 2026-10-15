import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from qualidock.app import create_app
from qualidock.executor import LocalExecutor
from qualidock.files import FileAccess, PathViolation
from qualidock.manager import RunManager, save_json
from qualidock.metrics import parse_report, parse_text
from conftest import DATA, NATIVE_MEMORY_SAMPLER


def wait(client, run_id, states=None, timeout=10):
    states = states or {"completed", "partial", "failed", "cancelled", "interrupted"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["state"] in states:
            return run
        time.sleep(0.02)
    raise AssertionError(f"Run did not reach {states}: {run}")


def start(client, root, mode="both", paths=None):
    response = client.post("/api/runs", json={"name": "Pilot cohort", "mode": mode, "paths": paths or [str(p) for p in sorted(root.glob("*.fastq"))], "threads": 1})
    assert response.status_code == 201, response.text
    return response.json()


def test_fastq_detection_and_pairs(client, setup):
    _, root = setup
    (root / "orphan_R1.fq.gz").write_bytes(b"fixture")
    (root / "single.fq").write_text("fixture")
    listing = client.get("/api/files", params={"path": str(root)}).json()
    pairs = [e for e in listing["entries"] if e["paired"]]
    assert len(pairs) == 2
    assert {e["read"] for e in pairs} == {"R1", "R2"}
    assert all(e["mate"] for e in pairs)
    assert not next(e for e in listing["entries"] if e["name"].startswith("orphan"))["paired"]


@pytest.mark.parametrize("escape", ["traversal", "symlink", "sibling", "relative"])
def test_path_boundaries(client, setup, escape):
    settings, root = setup
    outside = root.parent / "outside"
    outside.mkdir()
    path = str(root / ".." / "outside") if escape == "traversal" else str(outside) if escape == "sibling" else "data"
    if escape == "symlink":
        (root / "escaped").symlink_to(outside, target_is_directory=True)
        path = str(root / "escaped")
        listing = client.get("/api/files", params={"path": str(root)}).json()
        assert "escaped" not in {e["name"] for e in listing["entries"]}
    assert client.get("/api/files", params={"path": path}).status_code == 403


def test_auth_cookie_csrf_and_download(client, setup):
    settings, root = setup
    run = start(client, root)
    wait(client, run["id"])
    with TestClient(create_app(type(settings)(**{**settings.__dict__, "output": root.parent / "other-results"}))) as unauth:
        assert unauth.get("/api/config").status_code == 401
        assert unauth.get(f"/api/runs/{run['id']}/download", params={"path": "manifest.json"}).status_code == 401
        assert unauth.post("/api/session", json={"token": settings.token}).status_code == 403
        assert unauth.post("/api/session", json={"token": "wrong"}, headers={"X-QualiDock-Request": "1"}).status_code == 401
        login = unauth.post("/api/session", json={"token": settings.token}, headers={"X-QualiDock-Request": "1"})
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"] and "SameSite=strict" in login.headers["set-cookie"]
        assert unauth.get("/api/config").status_code == 200
        assert unauth.post("/api/runs", json={}, headers={"X-QualiDock-Request": "1", "Origin": "https://evil.example"}).status_code == 403
    assert client.get(f"/api/runs/{run['id']}/download", params={"path": "../../data/sample_R1_001.fastq"}).status_code == 403
    assert client.get(f"/api/runs/{run['id']}/download", params={"path": "inputs/0/fastqc_data.txt"}).status_code == 403
    response = client.get(f"/api/runs/{run['id']}/download", params={"path": "multiqc/multiqc_report.html"})
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-type"] == "application/octet-stream"
    assert "sandbox" in response.headers["content-security-policy"]


def test_pipeline_metrics_and_restart(client, setup):
    settings, root = setup
    original = {p.name: p.read_bytes() for p in root.iterdir()}
    run = wait(client, start(client, root)["id"])
    assert run["state"] == "completed", run
    assert run["sample_count"] == 2
    metrics = client.get(f"/api/runs/{run['id']}/metrics").json()
    sample = metrics["samples"][0]
    assert sample["total_sequences"] == 1000
    assert sample["status"] == "warn"  # A FastQC warning does not fail the execution.
    assert sample["per_base_quality"][1] == {"base": "2-5", "mean": 34.2, "median": 35, "lower_quartile": 32, "upper_quartile": 36, "percentile_10": 30, "percentile_90": 38}
    assert "MultiQC fixture completed" in client.get(f"/api/runs/{run['id']}/logs").json()["text"]
    assert original == {p.name: p.read_bytes() for p in root.iterdir()}
    manifest = json.loads((settings.output / run["id"] / "manifest.json").read_text())
    assert "test-session-secret" not in json.dumps(manifest)


def test_restores_results_after_restart(setup):
    settings, root = setup
    with TestClient(create_app(settings)) as client:
        client.headers.update({"Authorization": f"Bearer {settings.token}", "X-QualiDock-Request": "1"})
        run = wait(client, start(client, root)["id"])
    with TestClient(create_app(settings)) as client:
        client.headers.update({"Authorization": f"Bearer {settings.token}"})
        assert client.get("/api/runs").json()[0]["id"] == run["id"]
        assert len(client.get(f"/api/runs/{run['id']}/metrics").json()["samples"]) == 2
        assert client.get(f"/api/runs/{run['id']}/download", params={"path": "metrics.json"}).status_code == 200


def test_partial_and_failure(client, setup):
    _, root = setup
    broken = root / "broken.fastq"
    broken.write_text("invalid fixture")
    run = wait(client, start(client, root)["id"])
    assert run["state"] == "partial" and "code 1" in run["error"]
    failed = wait(client, start(client, root, paths=[str(broken)])["id"])
    assert failed["state"] == "failed" and failed["sample_count"] == 0


def test_fastqc_only_and_multiqc_only(client, setup):
    _, root = setup
    run = wait(client, start(client, root, mode="fastqc")["id"])
    assert run["state"] == "completed"
    assert not any(r["path"].endswith("multiqc_report.html") for r in run["reports"])
    report = root / "existing_fastqc.zip"
    with zipfile.ZipFile(report, "w") as archive:
        archive.writestr("existing_fastqc/fastqc_data.txt", DATA.format(filename="existing.fastq"))
    combined = wait(client, start(client, root, mode="multiqc", paths=[str(report)])["id"])
    assert combined["state"] == "completed" and combined["sample_count"] == 1


def test_command_injection_filename_is_literal(client, setup):
    settings, root = setup
    malicious = root / "reads;touch PWNED.fastq"
    malicious.write_text("@r\nACGT\n+\nIIII\n")
    run = wait(client, start(client, root, paths=[str(malicious)])["id"])
    assert run["state"] == "completed"
    assert not (settings.output / run["id"] / "PWNED.fastq").exists()
    assert client.get(f"/api/runs/{run['id']}/metrics").json()["samples"][0]["name"] == malicious.name


def test_resource_validation(client, setup):
    _, root = setup
    response = client.post("/api/runs", json={"paths": [str(root / "sample_R1_001.fastq")], "threads": 32})
    assert response.status_code == 400


def test_cancel_running_and_queued(client, setup):
    _, root = setup
    slow = root / "slow.fastq"
    slow.write_text("fixture")
    first = start(client, root, paths=[str(slow)])
    wait(client, first["id"], {"running"})
    second = start(client, root)
    assert second["state"] == "queued"
    assert client.post(f"/api/runs/{second['id']}/cancel").json()["state"] == "cancelled"
    assert client.post(f"/api/runs/{first['id']}/cancel").json()["state"] == "cancelled"
    assert wait(client, first["id"])["state"] == "cancelled"
    assert wait(client, second["id"])["state"] == "cancelled"


def test_restart_marks_unfinished_interrupted(setup):
    settings, _ = setup
    manager = RunManager(settings)
    manager.start()
    run_id = "a" * 32
    directory = settings.output / run_id
    directory.mkdir()
    save_json(directory / "manifest.json", {"id": run_id, "state": "running", "created_at": "2026-01-01", "reports": []})
    manager.lock.close()
    recovered = RunManager(settings)
    recovered.start()
    assert recovered.runs[run_id]["state"] == "interrupted"
    recovered.lock.close()


@pytest.mark.parametrize("prefix", ["/node/compute/8765", "/rnode/compute/8765"])
def test_proxy_prefix_cookies_api_and_download(setup, prefix):
    settings, root = setup
    settings.prefix = prefix
    settings.frontend.mkdir()
    (settings.frontend / "index.html").write_text('<script src="./assets/app.js"></script>')
    with TestClient(create_app(settings)) as client:
        assert client.get(prefix + "/").status_code == 200
        assert client.post(prefix + "/api/session", json={"token": settings.token}, headers={"X-QualiDock-Request": "1"}).status_code == 200
        assert client.get(prefix + "/api/config").status_code == 200
        client.headers.update({"Authorization": f"Bearer {settings.token}", "X-QualiDock-Request": "1"})
        run = wait(client, start(client, root)["id"])
        assert client.get(prefix + f"/api/runs/{run['id']}/download", params={"path": "metrics.json"}).status_code == 200


def test_registered_artifact_symlink_is_rejected(client, setup):
    settings, root = setup
    run = wait(client, start(client, root)["id"])
    path = settings.output / run["id"] / "metrics.json"
    path.unlink()
    path.symlink_to(root / "sample_R1_001.fastq")
    assert client.get(f"/api/runs/{run['id']}/download", params={"path": "metrics.json"}).status_code == 403
    assert client.get(f"/api/runs/{run['id']}/metrics").status_code == 403


def test_parser_never_extracts_zip_traversal(tmp_path):
    path = tmp_path / "report.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../report/fastqc_data.txt", DATA.format(filename="sample.fastq"))
        archive.writestr("../../escaped.txt", "must never extract")
    assert parse_report(path, "report")["total_sequences"] == 1000
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_malformed_metrics_rejected():
    with pytest.raises(ValueError):
        parse_text("<html>untrusted</html>", "bad")
    sample = parse_text(DATA.format(filename="sample").replace("32.5", "NaN"), "report")
    assert sample["per_base_quality"][0]["mean"] is None


def test_second_session_cannot_own_same_output(setup):
    settings, _ = setup
    first = RunManager(settings)
    first.start()
    second = RunManager(settings)
    with pytest.raises(RuntimeError):
        second.start()
    first.lock.close()


def test_executor_kills_process_group(tmp_path):
    async def scenario():
        executor = LocalExecutor(1024)
        code = "import subprocess,time;from pathlib import Path;p=subprocess.Popen(['sleep','30']);Path('child.pid').write_text(str(p.pid));time.sleep(30)"
        task = asyncio.create_task(executor.execute("job", [sys.executable, "-c", code], tmp_path, tmp_path / "log", 1))
        for _ in range(100):
            if (tmp_path / "child.pid").exists():
                break
            await asyncio.sleep(0.02)
        child = int((tmp_path / "child.pid").read_text())
        await executor.cancel("job")
        await task
        for _ in range(100):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                return
            await asyncio.sleep(0.02)
        # Linux may retain a killed child as a zombie until init reaps it.
        if sys.platform == "linux" and Path(f"/proc/{child}/stat").exists():
            assert Path(f"/proc/{child}/stat").read_text().split(") ")[1][0] == "Z"
        else:
            raise AssertionError("Cancelled child survived")
    asyncio.run(scenario())


def test_memory_budget_terminates_run(tmp_path, monkeypatch):
    async def over_budget(group):
        return 2 * 1024 * 1024
    monkeypatch.setattr(LocalExecutor, "group_memory", staticmethod(over_budget))
    async def scenario():
        executor = LocalExecutor(1)
        code = await executor.execute("limited", [sys.executable, "-c", "import time;time.sleep(30)"], tmp_path, tmp_path / "log", 1)
        assert code == 137
        assert "Resource limit exceeded" in (tmp_path / "log").read_text()
        assert not executor.processes
    asyncio.run(scenario())


def test_cancel_during_process_startup(tmp_path, monkeypatch):
    async def scenario():
        spawned = asyncio.Event()
        release = asyncio.Event()
        original = asyncio.create_subprocess_exec
        async def delayed(*args, **kwargs):
            process = await original(*args, **kwargs)
            spawned.set()
            await release.wait()
            return process
        monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed)
        executor = LocalExecutor(1024)
        task = asyncio.create_task(executor.execute("race", [sys.executable, "-c", "import time;time.sleep(30)"], tmp_path, tmp_path / "log", 1))
        await asyncio.wait_for(spawned.wait(), 5)
        await executor.cancel("race")
        release.set()
        assert await task == 130
        assert not executor.processes
    asyncio.run(scenario())


def test_linux_proc_rss_parser(tmp_path, monkeypatch):
    stat = tmp_path / "stat"
    fields = ["0"] * 22
    fields[0], fields[1], fields[2], fields[21] = "S", "1", "9999", "42"
    stat.write_text("123 (a process with spaces) " + " ".join(fields))
    monkeypatch.setattr(sys, "platform", "linux")
    original = Path.glob
    monkeypatch.setattr(Path, "glob", lambda path, pattern: iter([stat]) if str(path) == "/proc" else original(path, pattern))
    assert asyncio.run(NATIVE_MEMORY_SAMPLER(9999)) == 42 * os.sysconf("SC_PAGE_SIZE")
    assert asyncio.run(NATIVE_MEMORY_SAMPLER(1234)) == 0


def test_queued_input_change_is_rejected(client, setup):
    _, root = setup
    slow = root / "slow.fastq"
    slow.write_text("fixture")
    first = start(client, root, paths=[str(slow)])
    wait(client, first["id"], {"running"})
    path = root / "sample_R1_001.fastq"
    second = start(client, root, paths=[str(path)])
    path.write_text("changed after queueing")
    client.post(f"/api/runs/{first['id']}/cancel")
    run = wait(client, second["id"])
    assert run["state"] == "failed" and "Input changed" in run["error"]


def test_multiqc_failure_keeps_fastqc_metrics(client, setup):
    settings, root = setup
    Path(settings.multiqc).write_text(f"#!{sys.executable}\nimport sys;print('multiqc, version 1.35' if '--version' in sys.argv else 'MultiQC failed');sys.exit(0 if '--version' in sys.argv else 2)\n")
    run = wait(client, start(client, root)["id"])
    assert run["state"] == "partial"
    assert run["sample_count"] == 2 and "MultiQC exited with code 2" in run["error"]
    assert any(r["path"].endswith("_fastqc.zip") for r in run["reports"])


def test_session_shutdown_preserves_interrupted(setup):
    settings, root = setup
    slow = root / "slow.fastq"
    slow.write_text("fixture")
    with TestClient(create_app(settings)) as client:
        client.headers.update({"Authorization": f"Bearer {settings.token}", "X-QualiDock-Request": "1"})
        first = start(client, root, paths=[str(slow)])
        wait(client, first["id"], {"running"})
        second = start(client, root)
    for run_id in (first["id"], second["id"]):
        manifest = json.loads((settings.output / run_id / "manifest.json").read_text())
        assert manifest["state"] == "interrupted"


def test_sse_snapshot_and_authentication(client):
    async def snapshot():
        from starlette.requests import Request
        app = client.app
        route = next(route for route in app.routes if getattr(route, "path", None) == "/api/events")
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        response = await route.endpoint(Request({"type": "http", "method": "GET", "path": "/api/events", "headers": []}, receive))
        event = await anext(response.body_iterator)
        assert "event: runs\n" in event and "data: []\n\n" in event
        assert response.headers["x-accel-buffering"] == "no"
        await response.body_iterator.aclose()
    asyncio.run(snapshot())
    assert client.get("/api/events", headers={"Authorization": ""}).status_code == 401


def test_guardian_stops_qc_after_server_is_killed(tmp_path):
    child_code = "import subprocess,time;from pathlib import Path;p=subprocess.Popen(['sleep','30']);Path('orphan.pid').write_text(str(p.pid));time.sleep(30)"
    parent_code = f"""import asyncio,sys
from pathlib import Path
from qualidock.executor import LocalExecutor
async def memory(group): return 0
LocalExecutor.group_memory=staticmethod(memory)
directory=Path(sys.argv[1])
asyncio.run(LocalExecutor(1024).execute('guardian',[sys.executable,'-c',{child_code!r}],directory,directory/'guardian.log',1))
"""
    parent = subprocess.Popen([sys.executable, "-c", parent_code, str(tmp_path)])
    child = None
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "orphan.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        child = int((tmp_path / "orphan.pid").read_text())
        parent.kill()
        parent.wait(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                return
            if sys.platform == "linux" and Path(f"/proc/{child}/stat").exists() and Path(f"/proc/{child}/stat").read_text().split(") ")[1][0] == "Z":
                return
            time.sleep(0.02)
        raise AssertionError("QC child survived the server's abrupt exit")
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if child:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
