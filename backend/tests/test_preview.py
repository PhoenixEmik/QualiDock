"""HTTP boundary tests. Browser enforcement is tested separately with real reports."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from qualidock.app import create_app
from qualidock.preview import application_csp, REPORT_CSP
from test_workspace import start, wait


def preview(client, run_id, path="multiqc/multiqc_report.html", method="GET", prefix="", **kwargs):
    return client.request(method, prefix + "/api/report-preview", params={"run_id": run_id, "path": path}, **kwargs)


def test_registered_preview_is_inline_isolated_and_byte_identical(client, setup):
    settings, root = setup
    run = wait(client, start(client, root)["id"])
    for report in run["reports"]:
        path = report["path"]
        if not path.endswith(".html"):
            continue
        original = (settings.output / run["id"] / path).read_bytes()
        response = preview(client, run["id"], path)
        assert response.status_code == 200
        assert response.content == original
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert response.headers["content-disposition"].startswith("inline;")
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        policy = response.headers["content-security-policy"]
        assert policy == REPORT_CSP
        assert "sandbox allow-scripts;" in policy and "allow-same-origin" not in policy
        for directive in ("connect-src 'none'", "form-action 'none'", "base-uri 'none'", "frame-src 'none'", "object-src 'none'", "frame-ancestors 'self'"):
            assert directive in policy
        assert "camera=()" in response.headers["permissions-policy"]
        head = preview(client, run["id"], path, method="HEAD")
        assert head.status_code == 200 and not head.content
        assert head.headers["content-length"] == str(len(original))
        download = client.get(f"/api/runs/{run['id']}/download", params={"path": path})
        assert download.content == original
        assert download.headers["content-disposition"].startswith("attachment;")
        assert download.headers["content-type"] == "application/octet-stream"
        assert download.headers["x-frame-options"] == "DENY"
        assert download.headers["content-security-policy"] == "sandbox; default-src 'none'"


def test_preview_needs_auth_and_rejects_opaque_origins(client, setup):
    _, root = setup
    run = wait(client, start(client, root)["id"])
    for method in ("GET", "HEAD"):
        assert preview(client, run["id"], method=method, headers={"Authorization": ""}).status_code == 401
        for headers in ({"Origin": "null"}, {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
            assert preview(client, run["id"], method=method, headers=headers).status_code == 403
            assert client.get("/api/config", headers=headers).status_code == 403
    assert client.get("/api/config").status_code == 200


@pytest.mark.parametrize("path", ["manifest.json", "metrics.json", "analysis.log", "fastqc/sample_R1_001_fastqc.zip"])
def test_non_html_registered_artifacts_remain_download_only(client, setup, path):
    _, root = setup
    run = wait(client, start(client, root)["id"])
    assert preview(client, run["id"], path).status_code == 415
    assert client.get(f"/api/runs/{run['id']}/download", params={"path": path}).status_code == 200


@pytest.mark.parametrize("path", ["../../data/sample_R1_001.fastq", "/etc/passwd", "fastqc/../multiqc/multiqc_report.html", "unregistered.html", "multiqc\\multiqc_report.html", "multiqc/\x00.html", "%2e%2e/secret.html"])
def test_preview_rejects_arbitrary_and_traversal_paths(client, setup, path):
    settings, root = setup
    run = wait(client, start(client, root)["id"])
    (settings.output / run["id"] / "unregistered.html").write_text("not registered")
    assert preview(client, run["id"], path).status_code == 403


@pytest.mark.parametrize("target", ["file", "parent", "run"])
def test_preview_rejects_symlink_escapes(client, setup, target):
    settings, root = setup
    run = wait(client, start(client, root)["id"])
    directory = settings.output / run["id"]
    outside = root / "outside"
    outside.mkdir()
    (outside / "multiqc_report.html").write_text("must not be served")
    if target == "file":
        path = directory / "multiqc/multiqc_report.html"
        path.unlink()
        path.symlink_to(outside / "multiqc_report.html")
    else:
        path = directory / "multiqc" if target == "parent" else directory
        path.rename(path.with_name(path.name + "-original"))
        path.symlink_to(outside, target_is_directory=True)
    assert preview(client, run["id"]).status_code == 403


def test_preview_missing_artifact_or_analysis(client, setup):
    settings, root = setup
    run = wait(client, start(client, root)["id"])
    assert preview(client, "unknown").status_code == 404
    (settings.output / run["id"] / "multiqc/multiqc_report.html").unlink()
    assert preview(client, run["id"]).status_code == 404


@pytest.mark.parametrize("prefix, stripped", [("", False), ("/node/compute/8765", False), ("/rnode/compute/8765", True)])
def test_cookie_preview_proxy_and_restart_are_backward_compatible(setup, prefix, stripped):
    settings, root = setup
    settings.prefix = prefix
    settings.secure_cookie = True
    settings.frontend.mkdir()
    (settings.frontend / "index.html").write_text("<main>QualiDock</main>")
    with TestClient(create_app(settings), base_url="https://qc.example") as client:
        login = client.post(prefix + "/api/session", json={"token": settings.token}, headers={"X-QualiDock-Request": "1"})
        assert login.status_code == 200 and "Secure" in login.headers["set-cookie"]
        client.headers.update({"Authorization": f"Bearer {settings.token}", "X-QualiDock-Request": "1"})
        run = wait(client, start(client, root)["id"])
        client.headers.pop("Authorization")
        response = preview(client, run["id"], prefix=prefix)
        assert response.status_code == 200
        digest = hashlib.sha256(response.content).hexdigest()
        app = client.get(prefix + "/")
        policy = app.headers["content-security-policy"]
        assert f"frame-src qc.example{prefix}/api/report-preview;" in policy
        assert "script-src 'self';" in policy and "frame-ancestors 'none'" in policy
        assert app.headers["x-frame-options"] == "DENY"
        if stripped:
            # OOD strips the URL prefix before upstream; the browser still sends
            # the prefix-scoped cookie from its original public request.
            assert preview(client, run["id"], headers={"Cookie": "; ".join(f"{k}={v}" for k, v in client.cookies.items())}).status_code == 200
    with TestClient(create_app(settings), base_url="https://qc.example") as client:
        client.post(prefix + "/api/session", json={"token": settings.token}, headers={"X-QualiDock-Request": "1"})
        restored = preview(client, run["id"], prefix=prefix)
        assert restored.status_code == 200
        assert hashlib.sha256(restored.content).hexdigest() == digest


def test_policy_host_cannot_inject_sources():
    assert "frame-src 'none'" in application_csp("evil; script-src *", "")
    assert "frame-src [::1]:8765/api/report-preview;" in application_csp("[::1]:8765", "")
    assert "frame-src qc.example/node/compute%20name/8765/api/report-preview;" in application_csp("qc.example", "/node/compute name/8765")
