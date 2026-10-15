"""Parse reported values only. ZIP members are bounded and never extracted."""
import json
import math
from pathlib import Path
import zipfile

MAX_DATA = 32 * 1024 * 1024
STATUSES = {"pass", "warn", "fail"}


def number(value: str) -> float | int | None:
    try:
        if not value.strip():
            return None
        if value.strip().lstrip("+-").isdigit():
            return int(value)
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def parse_summary(text: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        fields = line.split("\t", 2)
        if len(fields) == 3:
            result.append({"name": fields[1], "status": fields[0].lower(), "filename": fields[2]})
    return result


def parse_text(text: str, source: str, summary: str = "") -> dict:
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
            current = {"name": parts[0], "status": parts[1].lower() if len(parts) > 1 and parts[1].lower() in STATUSES else "unknown", "columns": [], "rows": [], "metadata": [], "comments": [], "available": True}
            modules.append(current)
        elif current is not None and line.startswith("#"):
            fields = line[1:].split("\t")
            current["comments"].append(line[1:])
            if fields[0] == "Total Deduplicated Percentage":
                current["metadata"].append(fields)
            elif not current["columns"]:
                current["columns"] = fields
        elif current is not None and line:
            current["rows"].append(line.split("\t"))
    basic = next((m for m in modules if m["name"] == "Basic Statistics"), None)
    if basic is None or not version:
        raise ValueError("Not a valid FastQC data report")
    warnings = []
    summary_rows = parse_summary(summary)
    by_name = {m["name"]: m for m in modules}
    for entry in summary_rows:
        module = by_name.get(entry["name"])
        if module is None:
            module = {"name": entry["name"], "status": entry["status"] if entry["status"] in STATUSES else "unknown", "columns": [], "rows": [], "available": False, "metadata": [], "comments": []}
            modules.append(module)
        module["summary_status"] = entry["status"]
        if module["status"] != entry["status"]:
            warnings.append(f"Status disagreement for {entry['name']}: data={module['status']}, summary={entry['status']}")
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
            "encoding": stats.get("Encoding", ""), "basic_statistics": stats,
            "status": "fail" if "fail" in statuses else "warn" if "warn" in statuses else "unknown" if "unknown" in statuses else "pass",
            "modules": modules, "per_base_quality": bases, "summary": summary_rows, "warnings": warnings}


def bounded_text(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DATA:
        raise ValueError(f"Expected a regular report file of at most {MAX_DATA} bytes: {path.name}")
    with path.open("rb") as stream:
        raw = stream.read(MAX_DATA + 1)
    if len(raw) > MAX_DATA:
        raise ValueError("Report exceeds the size limit")
    return raw.decode("utf-8-sig")


def parse_report(path: Path, source: str) -> dict:
    if path.is_symlink():
        raise ValueError("Report symlinks are not accepted")
    summary = ""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            matches = [info for info in archive.infolist() if info.filename.endswith("/fastqc_data.txt") or info.filename == "fastqc_data.txt"]
            if len(matches) != 1:
                raise ValueError("Expected one bounded FastQC data file in archive")
            def read(info):
                if info.file_size > MAX_DATA:
                    raise ValueError("FastQC archive member exceeds the size limit")
                with archive.open(info) as stream:
                    raw = stream.read(MAX_DATA + 1)
                if len(raw) > MAX_DATA:
                    raise ValueError("FastQC archive member exceeds the size limit")
                return raw.decode("utf-8-sig")
            text = read(matches[0])
            summary_name = str(Path(matches[0].filename).with_name("summary.txt"))
            summaries = [info for info in archive.infolist() if info.filename == summary_name]
            if len(summaries) > 1:
                raise ValueError("Duplicate FastQC summary in archive")
            if summaries:
                summary = read(summaries[0])
    else:
        data = path / "fastqc_data.txt" if path.is_dir() else path
        text = bounded_text(data)
        sibling = data.with_name("summary.txt")
        if sibling.exists() or sibling.is_symlink():
            summary = bounded_text(sibling)
    return parse_text(text, source, summary)


def parse_multiqc(path: Path) -> dict:
    """Expose general-statistics values without scaling, rounding or recomputation."""
    data = json.loads(bounded_text(path))
    if not isinstance(data, dict):
        raise ValueError("Unsupported MultiQC JSON structure")
    headers = data.get("report_general_stats_headers", [])
    tables = data.get("report_general_stats_data", [])
    if not isinstance(headers, list) or not isinstance(tables, list):
        return {"columns": [], "rows": []}
    columns, rows = [], {}
    for index, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        metadata = headers[index] if index < len(headers) and isinstance(headers[index], dict) else {}
        keys = dict.fromkeys(key for values in table.values() if isinstance(values, dict) for key in values)
        for key in keys:
            column = metadata.get(key, {})
            if not isinstance(column, dict):
                column = {}
            column = {name: value if isinstance(value, str) else "" for name, value in column.items()}
            columns.append({"key": f"{index}:{key}", "title": column.get("title", key), "description": column.get("description", ""), "namespace": column.get("namespace", ""), "unit": column.get("suffix", ""), "raw_key": key})
        for sample, values in table.items():
            if not isinstance(values, dict):
                continue
            row = rows.setdefault(sample, {"sample": sample, "values": {}})
            for key, value in values.items():
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    if not isinstance(value, float) or math.isfinite(value):
                        row["values"][f"{index}:{key}"] = value
    return {"columns": columns, "rows": list(rows.values())}
