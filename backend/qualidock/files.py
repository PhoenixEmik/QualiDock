from pathlib import Path
import re

FASTQ = re.compile(r"\.(?:fastq|fq)(?:\.gz)?$", re.I)
PAIR = re.compile(r"^(.*?)([._-])(?:R)?([12])((?:[._-]00\d)?)$", re.I)


class PathViolation(ValueError):
    pass


class FileAccess:
    def __init__(self, roots: list[Path]):
        self.roots = [p.resolve(strict=True) for p in roots]
        if not self.roots or not all(p.is_dir() for p in self.roots):
            raise ValueError("Configure at least one existing directory root")

    def resolve(self, raw: str) -> Path:
        if "\x00" in raw or ".." in Path(raw).parts:
            raise PathViolation("Path traversal is not allowed")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise PathViolation("An absolute path within a configured root is required")
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise PathViolation("Path is unavailable") from exc
        if not any(resolved.is_relative_to(root) for root in self.roots):
            raise PathViolation("Path is outside the configured roots")
        return resolved

    def browse(self, raw: str, offset: int = 0, limit: int = 500) -> dict:
        directory = self.resolve(raw)
        if not directory.is_dir():
            raise PathViolation("Choose a directory")
        entries = []
        for path in directory.iterdir():
            if path.name.startswith("."):
                continue
            try:
                target = self.resolve(str(path))
                if not target.is_dir() and not target.is_file():
                    continue
                stat = target.stat()
                kind = "directory" if target.is_dir() else "fastq" if FASTQ.search(path.name) else "fastqc" if path.name.endswith("_fastqc.zip") or path.name == "fastqc_data.txt" else "file"
                stem = FASTQ.sub("", path.name)
                pair = PAIR.match(stem) if kind == "fastq" else None
                entries.append({"name": path.name, "path": str(path), "kind": kind,
                                "size": stat.st_size if target.is_file() else None,
                                "modified": stat.st_mtime, "read": f"R{pair[3]}" if pair else None,
                                "pair_key": str(directory / (pair[1] + pair[4])) if pair else None})
            except (PathViolation, OSError):
                continue
        # Only mark a pair when both mates are present, with exactly one candidate per read.
        groups: dict[str, dict[str, list[str]]] = {}
        for entry in entries:
            if entry["pair_key"]:
                groups.setdefault(entry["pair_key"], {}).setdefault(entry["read"], []).append(entry["path"])
        for entry in entries:
            group = groups.get(entry["pair_key"], {})
            entry["paired"] = len(group.get("R1", [])) == len(group.get("R2", [])) == 1
            entry["mate"] = group["R2" if entry["read"] == "R1" else "R1"][0] if entry["paired"] else None
        entries.sort(key=lambda e: (e["kind"] != "directory", e["name"].casefold()))
        parent = directory.parent if any(directory.parent.is_relative_to(r) for r in self.roots) else None
        return {"path": str(directory), "parent": str(parent) if parent else None,
                "entries": entries[offset:offset + limit], "total": len(entries)}
