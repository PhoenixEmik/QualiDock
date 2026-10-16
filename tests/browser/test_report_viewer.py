"""Real browser / real QC acceptance. Run explicitly after building the frontend.

Requires Playwright's browser binaries, FastQC 0.13.0 and MultiQC 1.35.
No report content or scientific results are replaced with mock QC output.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import threading
import time
import uuid

import httpx
import pytest
import uvicorn

from qualidock.app import create_app
from qualidock.config import Settings
from qualidock.manager import save_json

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "backend/tests/fixtures/fastqc-0.13.0"


class Workspace:
    def __init__(self, settings):
        self.settings = settings
        self.server = None
        self.thread = None
        self.port = 0

    def start(self):
        self.socket = socket.socket()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("127.0.0.1", self.port))
        self.port = self.socket.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(create_app(self.settings), log_level="warning", timeout_graceful_shutdown=1))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert self.server.started, "The validation server did not start"

    def stop(self):
        if self.server:
            self.server.should_exit = True
            self.thread.join(10)
            assert not self.thread.is_alive(), "Validation server did not shut down"
            self.socket.close()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}{self.settings.prefix}/"

    @contextmanager
    def api(self):
        with httpx.Client(base_url=self.base, headers={"Authorization": f"Bearer {self.settings.token}", "X-QualiDock-Request": "1"}, timeout=30) as client:
            yield client

    def finish(self, client, response):
        if isinstance(response, dict):
            # Browser tests have already asserted the POST response status.
            identifier = response["id"]
        else:
            assert response.status_code == 201, response.text
            identifier = response.json()["id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            run = client.get(f"api/runs/{identifier}").json()
            if run["state"] not in {"queued", "running"}:
                assert run["state"] == "completed", client.get(f"api/runs/{identifier}/logs").text
                return run
            time.sleep(.05)
        raise AssertionError("Actual QC tools timed out")


@pytest.fixture(scope="module", params=["", "/node/compute/8765", "/rnode/compute/8765"])
def workspace(tmp_path_factory, request):
    fastqc = shutil.which(os.environ.get("QUALIDOCK_FASTQC", "fastqc"))
    multiqc = shutil.which(os.environ.get("QUALIDOCK_MULTIQC", "multiqc"))
    assert fastqc and multiqc, "Real FastQC and MultiQC are required for browser acceptance"
    assert (ROOT / "frontend/dist/index.html").is_file(), "Build the actual frontend first"
    output = tmp_path_factory.mktemp("report-browser")
    project_output = tmp_path_factory.mktemp("project-output")
    settings = Settings(roots=[INPUTS, output], output_roots=[project_output], output=output, frontend=ROOT / "frontend/dist", token=secrets.token_urlsafe(32), kraken2=os.environ.get('QUALIDOCK_KRAKEN2','kraken2'), screening_databases=json.loads(os.environ.get('QUALIDOCK_SCREENING_DATABASES','[]')), prefix=request.param, cpus=1, memory_mb=4096, fastqc=fastqc, multiqc=multiqc)
    # An intentionally malicious HTML artifact is used only to probe the security
    # boundary, never as scientific QC data or as a substitute for genuine reports.
    malicious_id = uuid.uuid4().hex
    directory = output / malicious_id
    directory.mkdir()
    malicious_path = 'fastqc/<img src=x onerror=alert(1)>_fastqc.html'
    (directory / "fastqc").mkdir()
    (directory / malicious_path).write_text("""<!doctype html><title>Security probe</title><h1>Isolated security probe</h1><script>
function blocked(fn){try{fn();return false}catch(e){return e.name==='SecurityError'}}
window.probe={parentDOM:blocked(()=>parent.document.body),cookie:blocked(()=>document.cookie),storage:blocked(()=>localStorage),session:blocked(()=>sessionStorage)};
fetch('/api/config?report_attack=1',{credentials:'include'}).then(()=>probe.api=false).catch(()=>probe.api=true);
parent.postMessage({type:'qualidock-report-ready',html:'<img onerror=alert(1)>'},'*');
</script>""")
    save_json(directory / "manifest.json", {"id": malicious_id, "name": "Security probe", "state": "completed", "mode": "fastqc", "stage": "Finished", "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z", "started_at": None, "finished_at": None, "threads": 1, "inputs": [], "reports": [{"path": malicious_path, "size": (directory / malicious_path).stat().st_size}]})
    instance = Workspace(settings)
    instance.start()
    instance.malicious_id = malicious_id
    instance.malicious_path = malicious_path
    try:
        with instance.api() as client:
            tools = client.get("api/config").json()["tool_details"]
            assert tools["fastqc"]["version"] == "0.13.0"
            assert tools["multiqc"]["version"] == "1.35"
            paths = [str(path) for path in sorted(INPUTS.glob("*.fastq.gz"))]
            instance.fastqc = instance.finish(client, client.post("api/runs", json={"name": "Browser FastQC", "mode": "fastqc", "paths": paths}))
            instance.combined = instance.finish(client, client.post("api/runs", json={"name": "Browser combined", "mode": "both", "paths": paths}))
            instance.aggregated = instance.finish(client, client.post(f"api/runs/{instance.fastqc['id']}/multiqc"))
            instance.imported = instance.finish(client, client.post("api/runs", json={"name": "Browser imported", "mode": "multiqc", "paths": [str(output / instance.fastqc["id"] / "fastqc")]}))
        # A genuine completed result without the new optional pairing fields.
        historical = {**instance.fastqc, "id": uuid.uuid4().hex, "name": "Browser historical"}
        historical.pop("input_pairing", None)
        historical.pop("pairing_note", None)
        historical.pop("output_directory", None)
        historical.pop("output_root", None)
        shutil.copytree(output / instance.fastqc["id"], output / historical["id"])
        save_json(output / historical["id"] / "manifest.json", historical)
        instance.historical = historical
        instance.stop()
        instance.start()
        yield instance
    finally:
        instance.stop()


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as runtime:
        browser = getattr(runtime, os.environ.get("QUALIDOCK_BROWSER", "chromium")).launch()
        yield browser
        browser.close()


def open_run(page, workspace, name):
    # A new query forces a document navigation, including after server restart;
    # changing only the fragment would leave the previous React session mounted.
    page.goto(workspace.base + "?browser-test=" + secrets.token_hex(4) + "#token=" + workspace.settings.token)
    page.get_by_role("button", name="Results", exact=True).click()
    page.get_by_role("button", name="Open " + name, exact=True).click()
    page.get_by_role("tab", name="Reports", exact=True).click()
    page.locator(".report-preview[aria-busy=false] iframe").wait_for()
    return page.locator(".report-preview iframe").content_frame


def quality_plot(frame):
    # MultiQC also creates a hidden General Statistics violin plot. A global
    # .first() locator waits for that hidden SVG forever; navigate to a specific
    # genuine FastQC plot instead of weakening the assertion or report sandbox.
    frame.locator('a[href="#fastqc_per_base_sequence_quality"]').first.click()
    plot = frame.locator("#fastqc_per_base_sequence_quality_plot")
    plot.scroll_into_view_if_needed()
    plot.locator(".main-svg").first.wait_for(timeout=30000)
    return plot


def test_real_reports_and_interactions(workspace, browser):
    with browser.new_context(viewport={"width": 1440, "height": 1000}) as context:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        frame = open_run(page, workspace, "Browser combined")
        assert page.get_by_label("Select HTML report").input_value() == "multiqc/multiqc_report.html"
        assert page.locator(".report-preview iframe").get_attribute("sandbox") == "allow-scripts"
        assert page.locator(".report-preview iframe").get_attribute("referrerpolicy") == "no-referrer"
        # Genuine MultiQC 1.35: compressed plot data, Plotly figures and tables.
        assert frame.locator("#general_stats_table_table tbody tr").count() >= 2
        chart = quality_plot(frame)
        assert frame.locator(".mqc_loading_warning").first.is_hidden()
        assert not errors, errors
        chart.hover()
        assert chart.locator(".modebar").count() > 0
        # Strict allow-scripts deliberately blocks native form submission before
        # MultiQC's submit handler. Keep this restriction visible and documented;
        # do not fake success by dispatching a synthetic submit in the test.
        hide = frame.locator("#mqc_hidesamples")
        assert hide.count() == 1
        toolbar_hide = frame.locator('a[href="#mqc_hidesamples"][title="Hide"]')
        toolbar_hide.first.click()
        hide_input = hide.locator("#mqc_hidesamples_filter")
        hide_input.fill("coverage_R1")
        hide.locator("#mqc_hidesamples_filter_update").click()
        assert hide.locator("#mqc_hidesamples_filters li").count() == 0
        assert "form-based controls" in page.locator(".report-preview-help").inner_text()
        page.get_by_role("button", name="Full-height view", exact=True).click()
        assert page.locator(".report-viewer-expanded").count() == 1
        html_path = next(report["path"] for report in workspace.combined["reports"] if report["path"].startswith("fastqc/") and report["path"].endswith(".html"))
        page.get_by_label("Select HTML report").select_option(html_path)
        page.locator(".report-preview[aria-busy=false] iframe").wait_for()
        frame = page.locator(".report-preview iframe").content_frame
        frame.get_by_text("FastQC Report", exact=False).first.wait_for()
        assert frame.locator("img").count() > 0
        assert frame.locator("img").evaluate_all("images => images.every(img => img.complete && img.naturalWidth > 0)")
        frame.get_by_role("link", name="Per base sequence quality").first.click()
        assert frame.locator("h2").filter(has_text="Per base sequence quality").is_visible()
        with page.expect_download() as download:
            page.locator(".report-viewer-toolbar").get_by_role("link", name="Download", exact=True).click()
        original = workspace.settings.output / workspace.combined["id"] / html_path
        assert hashlib.sha256(Path(download.value.path()).read_bytes()).digest() == hashlib.sha256(original.read_bytes()).digest()
        # Narrow layouts preserve the real viewer without horizontal page overflow.
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_opaque_report_cannot_read_parent_or_private_state(workspace, browser):
    with browser.new_context() as context:
        page = context.new_page()
        dialogs = []
        page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
        open_run(page, workspace, "Security probe")
        frame = page.locator(".report-preview iframe").element_handle().content_frame()
        frame.wait_for_function("window.probe && probe.api !== undefined")
        assert frame.evaluate("window.probe") == {"parentDOM": True, "cookie": True, "storage": True, "session": True, "api": True}
        assert page.locator(".report-viewer-toolbar img").count() == 0
        assert not dialogs
        assert "<img" in page.get_by_label("Select HTML report").input_value()
        assert context.request.get(workspace.base + "api/config").status == 200
        anonymous = browser.new_context()
        try:
            response = anonymous.request.get(workspace.base + "api/report-preview", params={"run_id": workspace.malicious_id, "path": workspace.malicious_path})
            assert response.status == 401
        finally:
            anonymous.close()


def test_multiqc_temporary_state_never_exposes_parent_storage_or_cookies(workspace, browser):
    with browser.new_context() as context:
        page = context.new_page()
        open_run(page, workspace, "Browser combined")
        page.evaluate("localStorage.setItem('qualidock-parent-canary','private'); sessionStorage.setItem('qualidock-parent-canary','private')")
        frame = page.locator(".report-preview iframe").content_frame
        quality_plot(frame)
        boundary = frame.locator("body").evaluate("""() => {
          function blocked(fn){try{fn();return false}catch(error){return error.name==='SecurityError'}}
          return {parentDOM:blocked(()=>parent.document.body),parentCookie:blocked(()=>parent.document.cookie),cookie:document.cookie,local:localStorage.getItem('qualidock-parent-canary'),session:sessionStorage.getItem('qualidock-parent-canary')};
        }""")
        assert boundary == {"parentDOM": True, "parentCookie": True, "cookie": "", "local": None, "session": None}
        frame.locator("body").evaluate("() => {localStorage.setItem('mqc-theme','dark'); sessionStorage.setItem('report-only','value'); document.cookie='preview_only=must-not-persist'}")
        assert frame.locator("body").evaluate("() => localStorage.getItem('mqc-theme')") == "dark"
        assert page.evaluate("localStorage.getItem('mqc-theme')") is None
        assert not any(cookie["name"] == "preview_only" for cookie in context.cookies())
        assert frame.locator("body").evaluate("""async () => {try{await fetch('/api/config',{credentials:'include'});return false}catch(_){return true}}""")
        page.reload()
        page.get_by_role("button", name="Results", exact=True).click()
        page.get_by_role("button", name="Open Browser combined", exact=True).click()
        page.get_by_role("tab", name="Reports", exact=True).click()
        page.locator(".report-preview[aria-busy=false] iframe").wait_for()
        frame = page.locator(".report-preview iframe").content_frame
        quality_plot(frame)
        assert frame.locator("body").evaluate("() => localStorage.getItem('mqc-theme')") is None
        assert frame.locator("body").evaluate("() => sessionStorage.getItem('report-only')") is None
        assert page.evaluate("localStorage.getItem('qualidock-parent-canary')") == "private"


def test_loading_missing_reports_and_restart(workspace, browser):
    with browser.new_context() as context:
        page = context.new_page()
        for run in (workspace.fastqc, workspace.aggregated, workspace.imported):
            open_run(page, workspace, run["name"])
            if run["mode"] == "multiqc":
                frame = page.locator(".report-preview iframe").content_frame
                quality_plot(frame)
        workspace.stop()
        workspace.start()
        open_run(page, workspace, "Browser combined")
        frame = page.locator(".report-preview iframe").content_frame
        quality_plot(frame)
        # HTTP errors are checked before embedding, even though onLoad alone
        # cannot distinguish an opaque error page from a successfully loaded report.
        page.route("**/api/report-preview?*", lambda route: route.fulfill(status=404) if route.request.method == "HEAD" else route.continue_())
        page.get_by_label("Select HTML report").select_option(next(report["path"] for report in workspace.combined["reports"] if report["path"].startswith("fastqc/") and report["path"].endswith(".html")))
        page.get_by_text("This saved report is no longer available.", exact=False).wait_for()
        assert page.locator(".report-preview iframe").count() == 0
        page.unroute("**/api/report-preview?*")
        page.get_by_role("button", name="Retry preview").click()
        page.locator(".report-preview[aria-busy=false] iframe").wait_for()
