from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from qualidock.app import create_app
from qualidock.files import FileAccess
from test_workspace import start, wait


def test_analysis_preserves_explorer_confirmed_pairs_and_history(setup):
    settings, root = setup
    with TestClient(create_app(settings)) as client:
        client.headers.update({"Authorization": f"Bearer {settings.token}", "X-QualiDock-Request": "1"})
        expected = FileAccess([root]).pairing(sorted(root.glob("*.fastq")))
        run = wait(client, start(client, root)["id"])
        assert run["state"] == "completed"
        assert [{key: record[key] for key in expected[0]} for record in run["input_pairing"]] == expected
        assert all(record['source'] == 'auto' and record['assignment'] == 'paired' for record in run['input_pairing'])
        persisted = run['input_pairing']
        assert {record["read"] for record in expected} == {"R1", "R2"}
        assert all(record["paired"] and record["mate"] for record in expected)
        assert set(expected[0]) == {"path", "name", "read", "pair_key", "paired", "mate", "lane", "chunk", "ambiguous"}
        metrics = client.get(f"/api/runs/{run['id']}/metrics").json()
        assert {sample["name"] for sample in metrics["samples"]} == {record["name"] for record in expected}
    with TestClient(create_app(settings)) as client:
        client.headers.update({"Authorization": f"Bearer {settings.token}"})
        assert client.get(f"/api/runs/{run['id']}").json()["input_pairing"] == persisted
        assert client.get(f"/api/runs/{run['id']}/metrics").json() == metrics


def test_ambiguous_unselected_names_are_not_ignored(setup):
    _, root = setup
    paths = sorted(root.glob("*.fastq"))
    (root / "sample_1_001.fastq").write_text("@read\nACGT\n+\nIIII\n")
    records = FileAccess([root]).pairing(paths)
    assert len(records) == 2
    assert not any(record["paired"] or record["mate"] for record in records)


def test_multiple_lanes_and_chunks_remain_independent(setup):
    _, root = setup
    for lane in ("L001", "L002"):
        for chunk in ("001", "002"):
            for read in (1, 2):
                (root / f"sample_{lane}_R{read}_{chunk}.fq.gz").write_bytes(b"metadata-only pairing test")
    records = FileAccess([root]).pairing(sorted(root.glob("*.fq.gz")))
    assert len({record["pair_key"] for record in records}) == 4
    assert all(record["paired"] for record in records)
    for record in records:
        assert Path(record["mate"]).name.replace("R1", "R2") == record["name"].replace("R1", "R2")


@pytest.mark.parametrize("missing", [1, 2])
def test_incomplete_and_single_end_inputs_survive(setup, missing):
    _, root = setup
    (root / f"sample_R{missing}_001.fastq").unlink()
    (root / "unassigned.fastq").write_text("@read\nACGT\n+\nIIII\n")
    records = FileAccess([root]).pairing(sorted(root.glob("*.fastq")))
    assert len(records) == 2
    assert not any(record["paired"] or record["mate"] for record in records)
    assert next(record for record in records if record["name"] == "unassigned.fastq")["read"] is None


def test_pairing_does_not_read_fastq_contents(setup, monkeypatch):
    _, root = setup
    def fail(*args, **kwargs):
        raise AssertionError("Pair detection must not load source FASTQ bytes")
    monkeypatch.setattr(Path, "read_bytes", fail)
    monkeypatch.setattr(Path, "read_text", fail)
    assert all(record["paired"] for record in FileAccess([root]).pairing(sorted(root.glob("*.fastq"))))


def test_optional_pairing_failure_does_not_block_existing_fastqc(client, setup, monkeypatch):
    _, root = setup
    def unavailable(*args):
        raise ValueError("Directory exceeds the browsing index limit")
    monkeypatch.setattr(client.app.state.manager.files, "pairing", unavailable)
    run = wait(client, start(client, root, mode="fastqc")["id"])
    assert run["state"] == "completed" and run["sample_count"] == 2
    assert run["input_pairing"] == [] and run["pairing_note"]


def test_escaped_mate_never_confirms_pair(setup):
    _, root = setup
    mate = root / "sample_R2_001.fastq"
    mate.unlink()
    outside = root.parent / "outside.fastq"
    outside.write_text("@read\nACGT\n+\nIIII\n")
    mate.symlink_to(outside)
    record = FileAccess([root]).pairing([root / "sample_R1_001.fastq"])[0]
    assert not record["paired"] and record["mate"] is None
