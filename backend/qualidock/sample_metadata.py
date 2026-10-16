"""File relationships only. No sequencing data is read, merged or calculated here."""
import hashlib
from pathlib import Path
import re

FASTQ_SUFFIX = re.compile(r"\.(?:fastq|fq)(?:\.gz)?$", re.I)
PAIR_NAME = re.compile(r"^(.*?)([._-])(?:R)?([12])((?:[._-]\d{3})?)$", re.I)
SOURCES = {"auto", "confirmed", "manual"}


def identity(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def describe(path):
    path = Path(path)
    match = PAIR_NAME.match(FASTQ_SUFFIX.sub("", path.name))
    if not match:
        return {"sample_key": None, "sample_name": path.name, "lane": None, "chunk": None}
    prefix, chunk = match[1], match[4][1:] or None
    lane_match = re.search(r"_L(\d{3})$", prefix, re.I)
    lane = 'L' + lane_match[1] if lane_match else None
    sample = prefix[:lane_match.start()] if lane_match else prefix
    # Keep S-number in the identity, but never use S1 by itself as a sample name.
    display = re.sub(r"_S\d+$", "", sample, flags=re.I)
    if not display or re.fullmatch(r"S\d+", display, re.I):
        return {"sample_key": None, "sample_name": path.name, "lane": lane, "chunk": chunk}
    return {"sample_key": str(path.parent / sample), "sample_name": display, "lane": lane, "chunk": chunk}


def auto_groups(records):
    groups = {}
    for record in records:
        details = describe(record['path'])
        key = record['pair_key'] if record.get('source') == 'manual' and record.get('paired') else details['sample_key'] if not record.get('ambiguous') else None
        key = key or record['path']
        group_id = 'sample:' + identity(key)
        group = groups.setdefault(group_id, {"id": group_id, "display_name": details['sample_name'] if details['sample_key'] and not record.get('ambiguous') else record['name'], "files": [], "source": "manual" if record.get("source") == "manual" and record.get("paired") else "auto"})
        group['display_name'] = group['display_name'][:120]
        group['files'].append(record['path'])
    return list(groups.values())


def validate_configuration(paths, automatic, pairing=None, groups=None, *, detected_groups=None):
    """Validate a complete, explicit assignment against current canonical inputs."""
    allowed = {str(path) for path in paths}
    by_path = {record['path']: record for record in automatic}
    records = automatic if pairing is None else pairing
    if not isinstance(records, list) or len(records) != len(allowed):
        raise ValueError('Pairing metadata must contain each selected FASTQ exactly once')
    result, seen, pairs = [], set(), {}
    for value in records:
        if not isinstance(value, dict):
            raise ValueError('Invalid pairing metadata')
        path = value.get('path')
        if path not in allowed or path in seen:
            raise ValueError('Pairing references an unselected or duplicate FASTQ')
        seen.add(path)
        source = value.get('source', 'auto')
        if source not in SOURCES:
            raise ValueError('Invalid pairing provenance')
        assignment = value.get('assignment', 'paired' if value.get('paired') else 'unpaired')
        if assignment not in {'paired', 'single', 'unpaired'}:
            raise ValueError('Invalid read assignment')
        record = {"path": path, "name": Path(path).name, "source": source, "assignment": assignment,
                  "read": value.get('read'), "pair_key": value.get('pair_key'), "paired": assignment == 'paired', "mate": value.get('mate'),
                  "ambiguous": bool(by_path.get(path, {}).get("ambiguous")), "lane": value.get('lane', describe(path)['lane']), "chunk": value.get('chunk', describe(path)['chunk'])}
        for field in ('lane', 'chunk'):
            if record[field] is not None and (not isinstance(record[field], str) or len(record[field]) > 80 or any(ord(c) < 32 for c in record[field])):
                raise ValueError('Lane and chunk labels must be short text')
        if record['paired']:
            if record['read'] not in {'R1', 'R2'} or record['mate'] not in allowed or record['mate'] == path:
                raise ValueError('A pair requires two different selected FASTQ files with R1 and R2')
            if not isinstance(record['pair_key'], str) or not 1 <= len(record['pair_key']) <= 2048:
                raise ValueError('A pair requires an identity')
            pairs.setdefault(record['pair_key'], []).append(record)
            if source in {'auto', 'confirmed'}:
                expected = by_path.get(path, {})
                if not expected.get('paired') or expected.get('mate') != record['mate'] or expected.get('read') != record['read']:
                    raise ValueError('Automatic/confirmed pairing must match current unambiguous detection; use manual provenance for corrections')
        else:
            record.update(read=record["read"] if source == "auto" and assignment == "unpaired" and record["read"] in {"R1", "R2"} else None, pair_key=None, mate=None)
        result.append(record)
    for members in pairs.values():
        if len(members) != 2 or {v['read'] for v in members} != {'R1', 'R2'} or members[0]['mate'] != members[1]['path'] or members[1]['mate'] != members[0]['path']:
            raise ValueError('Conflicting or incomplete read pair assignment')
        if any(members[0][field] != members[1][field] for field in ('source', 'lane', 'chunk')):
            raise ValueError('Both reads must agree on pair provenance, lane and chunk')
    groups = (detected_groups if detected_groups is not None else auto_groups(result)) if groups is None else groups
    if not isinstance(groups, list) or len(groups) > 500:
        raise ValueError('Invalid sample groups')
    normalized_groups, members, identifiers = [], set(), set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9_:.-]{1,128}', group['id']) or group['id'] in identifiers:
            raise ValueError('Sample groups require unique stable identities')
        name, files = group.get('display_name'), group.get('files')
        if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 for c in name):
            raise ValueError('Sample display names must contain 1–120 printable characters')
        if not isinstance(files, list) or not files or any(not isinstance(path, str) or path not in allowed or path in members for path in files) or len(set(files)) != len(files):
            raise ValueError('Each selected FASTQ must belong to exactly one sample group')
        members.update(files)
        identifiers.add(group['id'])
        source = group.get('source', 'auto')
        if source not in SOURCES:
            raise ValueError('Invalid sample grouping provenance')
        if source in {'auto', 'confirmed'}:
            expected = next((candidate for candidate in (detected_groups if detected_groups is not None else auto_groups(automatic)) if candidate['id'] == group['id']), None)
            if not expected or set(expected['files']) != set(files) or expected['display_name'] != name.strip():
                raise ValueError('Automatic/confirmed sample groups must match detection; use manual provenance for changes')
        normalized_groups.append({"id": group['id'], "display_name": name.strip(), "files": files, "source": source})
    if members != allowed:
        raise ValueError('Each selected FASTQ must belong to exactly one sample group')
    membership = {path: group['id'] for group in normalized_groups for path in group['files']}
    if any(membership[pair[0]['path']] != membership[pair[1]['path']] for pair in pairs.values()):
        raise ValueError('Both reads of a pair must belong to the same sample group')
    return {"input_pairing": result, "sample_groups": normalized_groups}
