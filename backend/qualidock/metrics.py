"""Parse bounded FastQC text/ZIP data without rendering HTML or extracting archives."""
import math
from pathlib import Path
import zipfile

MAX_DATA = 32 * 1024 * 1024


def number(value: str) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def parse_text(text: str, source: str) -> dict:
    modules = []
    current = None
    version = None
    for line in text.splitlines():
        if line.startswith("##FastQC"):
            version = line.split("\t")[-1]
        elif line == ">>END_MODULE":
            current = None
        elif line.startswith(">>"):
            parts = line[2:].split("\t")
            current = {"name": parts[0], "status": parts[1].lower() if len(parts) > 1 and parts[1].lower() in {"pass", "warn", "fail"} else "unknown", "columns": [], "rows": []}
            modules.append(current)
        elif current is not None and line.startswith("#"):
            current["columns"] = line[1:].split("\t")
        elif current is not None and line:
            current["rows"].append(line.split("\t"))
    basic = next((m for m in modules if m["name"] == "Basic Statistics"), None)
    if basic is None or not version:
        raise ValueError("Not a valid FastQC data report")
    stats = {row[0]: row[1] for row in basic["rows"] if len(row) >= 2}
    quality = next((m for m in modules if m["name"] == "Per base sequence quality"), None)
    bases = []
    if quality:
        for row in quality["rows"]:
            if len(row) < 7:
                raise ValueError("Malformed per-base quality row")
            bases.append(dict(zip(("base", "mean", "median", "lower_quartile", "upper_quartile", "percentile_10", "percentile_90"), [row[0], *[number(v) for v in row[1:7]]])))
    statuses = [m["status"] for m in modules]
    return {"id": source, "name": stats.get("Filename", Path(source).stem), "fastqc_version": version,
            "total_sequences": number(stats.get("Total Sequences", "")),
            "gc_percent": number(stats.get("%GC", "")), "sequence_length": stats.get("Sequence length", ""),
            "encoding": stats.get("Encoding", ""),
            "status": "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass",
            "modules": modules, "per_base_quality": bases}


def parse_report(path: Path, source: str) -> dict:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            matches = [info for info in archive.infolist() if info.filename.endswith("/fastqc_data.txt")]
            if len(matches) != 1 or matches[0].file_size > MAX_DATA:
                raise ValueError("Expected one bounded FastQC data file in archive")
            raw = archive.read(matches[0])
    else:
        if path.stat().st_size > MAX_DATA:
            raise ValueError("FastQC data report is too large")
        raw = path.read_bytes()
    return parse_text(raw.decode("utf-8"), source)
