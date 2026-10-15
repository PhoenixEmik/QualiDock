"""Native FastQC interactions against the same genuine-tool acceptance workspace."""
import csv
import io
from pathlib import Path
import re

from test_report_viewer import browser, workspace, open_run, playwright

expect = playwright.expect


def test_modules_comparison_raw_exports_and_keyboard(workspace, browser):
    with workspace.api() as client:
        before = client.get(f"api/runs/{workspace.combined['id']}").json()
        samples = client.get(f"api/runs/{workspace.combined['id']}/metrics").json()["samples"]
    with browser.new_context(viewport={"width": 1440, "height": 1000}) as context:
        page = context.new_page()
        open_run(page, workspace, "Browser combined")
        page.get_by_role("tab", name="QC metrics", exact=True).click()
        page.get_by_role("button", name="Sample Details", exact=True).click()
        page.get_by_label("Select FASTQ sample").select_option(samples[0]["id"])
        navigation = page.get_by_role("navigation", name="FastQC modules")
        assert navigation.get_by_role("button").count() >= 12
        for module in samples[0]["modules"]:
            button = navigation.get_by_role("button", name=re.compile("^" + re.escape(module["name"])))
            button.focus()
            button.press("Enter")
            expect(page.locator("#qc-metric-heading")).to_have_text(module["name"])
            expect(page.locator("#qc-metric-heading")).to_be_focused()
        metric = "Per base sequence quality"
        navigation.get_by_role("button", name=re.compile("^" + metric)).click()
        page.get_by_role("button", name="R1 / R2 Comparison", exact=True).click()
        expect(page.get_by_role("button", name="R1 / R2 Comparison", exact=True)).to_have_attribute("aria-pressed", "true")
        expect(page.get_by_label("Select confirmed pair")).to_be_visible()
        for label in ("R1 · Mean", "R2 · Mean"):
            series = page.get_by_label(label, exact=True)
            expect(series).to_be_checked()
            series.uncheck()
            expect(series).not_to_be_checked()
            series.check()
        page.get_by_label("Show reported medians").check()
        expect(page.get_by_label("R1 · Median", exact=True)).to_be_visible()
        expect(page.get_by_label("R2 · Median", exact=True)).to_be_visible()
        page.get_by_text("About this module", exact=True).click()
        expect(page.get_by_text("Aggregate quality summaries cannot determine exact Q20/Q30", exact=False)).to_be_visible()
        raw = page.locator("details.qc-raw-data").first
        raw.locator("summary").click()
        module = next(module for module in samples[0]["modules"] if module["name"] == metric)
        expect(raw.locator("thead th")).to_have_count(len(module["columns"]))
        assert raw.locator("thead th").all_text_contents() == module["columns"]
        assert raw.locator("tbody tr").first.locator("td").all_text_contents() == module["rows"][0]
        for extension, delimiter in (("CSV", ","), ("TSV", "\t")):
            with page.expect_download() as download:
                raw.get_by_role("button", name="Export " + extension).click()
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
            writer.writerows([module["columns"], *module["rows"]])
            assert Path(download.value.path()).read_bytes() == buffer.getvalue().encode()
        page.get_by_role("button", name="Hide sample details", exact=True).click()
        expect(page.locator("#sample-details")).to_be_hidden()
        assert navigation.get_by_role("button").count() >= 12
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expect(page.locator(".quality-chart")).to_be_visible()
        page.get_by_role("button", name="Single Sample", exact=True).click()
        expect(page.get_by_label("Select FASTQ sample")).to_be_visible()
    with workspace.api() as client:
        assert client.get(f"api/runs/{workspace.combined['id']}").json()["executions"] == before["executions"]


def test_historical_without_pairing_keeps_individual_results(workspace, browser):
    with browser.new_context() as context:
        page = context.new_page()
        open_run(page, workspace, "Browser historical")
        page.get_by_role("tab", name="QC metrics", exact=True).click()
        page.get_by_role("button", name="Sample Details", exact=True).click()
        expect(page.get_by_role("button", name="R1 / R2 Comparison", exact=True)).to_be_disabled()
        expect(page.get_by_text("No confirmed pair is available.", exact=False)).to_be_visible()
        expect(page.get_by_label("Select FASTQ sample")).to_be_visible()
        expect(page.locator(".quality-chart")).to_be_visible()
