#!/usr/bin/env python3
"""Real-tool acceptance smoke; never substitutes mocked QC executables."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings

for tool in ("fastqc", "multiqc"):
    if shutil.which(tool) is None:
        raise SystemExit(f"Install {tool} before running this real-tool smoke test.")
root = Path("example-data").resolve(strict=True)
inputs = sorted(root.glob("pilot_01_*.fastq.gz"))
if len(inputs) != 2:
    raise SystemExit("Run scripts/create-example-data.py first.")
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
original = {str(p): digest(p) for p in inputs}
with tempfile.TemporaryDirectory(prefix="qualidock-smoke-") as output:
    settings = Settings(roots=[root], output=Path(output), frontend=Path("frontend/dist"), token="smoke-test-only", cpus=1, memory_mb=4096)
    with TestClient(create_app(settings)) as client:
        client.headers.update({"Authorization": f"Bearer {settings.token}", "X-QualiDock-Request": "1"})
        response = client.post("/api/runs", json={"name": "Real paired-end acceptance smoke", "mode": "both", "paths": list(original), "threads": 1})
        assert response.status_code == 201, response.text
        run_id = response.json()["id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            run = client.get(f"/api/runs/{run_id}").json()
            if run["state"] not in {"running", "queued"}:
                break
            time.sleep(0.3)
        assert run["state"] == "completed", client.get(f"/api/runs/{run_id}/logs").json()
        metrics = client.get(f"/api/runs/{run_id}/metrics").json()
        assert len(metrics["samples"]) == 2
        for sample in metrics["samples"]:
            assert sample["per_base_quality"]
            assert all(0 <= row["mean"] <= 45 for row in sample["per_base_quality"])
        for report in ("multiqc/multiqc_report.html", "metrics.json", "manifest.json"):
            assert client.get(f"/api/runs/{run_id}/download", params={"path": report}).status_code == 200
    with TestClient(create_app(settings)) as restored:
        restored.headers.update({"Authorization": f"Bearer {settings.token}"})
        assert restored.get("/api/runs").json()[0]["state"] == "completed"
        assert len(restored.get(f"/api/runs/{run_id}/metrics").json()["samples"]) == 2
    assert original == {str(p): digest(p) for p in inputs}
print("PASS: real FastQC + MultiQC, paired-end inputs, metrics, downloads, immutable inputs, restart recovery")
