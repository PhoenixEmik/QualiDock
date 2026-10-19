"""Pure report-contract tests for the upcoming RSeQC gene-body operation.

These are not substitutes for the genuine, indexed-BAM tool-study in CI.
"""
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "qualify-rseqc-genebody.py"
SPEC = importlib.util.spec_from_file_location("rseqc_gene_body_qualification", SCRIPT)
QUALIFICATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUALIFICATION)


def report(tmp_path, values, header=None, sample="input"):
    path = tmp_path / "profile.geneBodyCoverage.txt"
    labels = header if header is not None else [str(n) for n in range(1, 101)]
    path.write_text("Percentile\t" + "\t".join(labels) + "\n"
                    + sample + "\t" + "\t".join(values) + "\n")
    return path


def test_original_percentile_strings_and_sha_are_preserved(tmp_path):
    values = ["0.0"] * 99 + ["123.125"]
    path = report(tmp_path, values)
    result = QUALIFICATION.parse_profile(path)
    assert result["sample"] == "input" and result["percentiles"] == 100
    assert result["first"] == "0.0" and result["last"] == "123.125"
    assert result["minimum"] == 0 and result["maximum"] == 123.125
    assert result["all_zero"] is False
    assert result["raw_sha256"] == QUALIFICATION.digest(path)


@pytest.mark.parametrize("fault", [
    "nonfinite", "negative", "fewer-columns", "wrong-order",
    "extra-sample", "empty-sample", "oversized", "missing-sample",
])
def test_invalid_or_ambiguous_upstream_profile_is_not_qualified(tmp_path, fault):
    values = ["1"] * 100
    labels = None
    sample = "input"
    if fault == "nonfinite":
        values[10] = "nan"
    elif fault == "negative":
        values[10] = "-1"
    elif fault == "fewer-columns":
        values.pop()
    elif fault == "wrong-order":
        labels = ["2", "1", *map(str, range(3, 101))]
    elif fault == "empty-sample":
        sample = ""
    path = report(tmp_path, values, labels, sample)
    if fault == "extra-sample":
        path.write_text(path.read_text() + "other\t" + "\t".join(values) + "\n")
    elif fault == "missing-sample":
        path.write_text(path.read_text().splitlines()[0] + "\n")
    elif fault == "oversized":
        path.write_bytes(path.read_bytes() + b"x" * (1024 * 1024 + 1))
    with pytest.raises(ValueError):
        QUALIFICATION.parse_profile(path)
