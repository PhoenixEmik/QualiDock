"""Traceable file inventory, explicit delivery expectations and quantity targets.

Only additive counts are aggregated. No QC distributions or biological identities
are inferred, and absent metrics never become zero or a passing target.
"""
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata

from .outcomes import plan

EXPECTED_FIELDS = {'file_id','path','filename','sample_id','sample_name','lane','chunk','read','expected_reads','expected_bases','sha256'}
CSV_FIELDS = ['file_id','sample_id','sample_name','lane','chunk','read','filename','input_reference','size_bytes','size_source','sequence_length','reads','bases','q20_bases','q30_bases','quality_bases','counts_source','sha256','checksum_status','integrity_state','input_available']
INTEGER_LIMIT = 2**53 - 1


def integer(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value <= INTEGER_LIMIT:
        return value
    if isinstance(value, float) and value.is_integer() and 0 <= value <= INTEGER_LIMIT:
        return int(value)
    return None


def parse_expected(content, format):
    if len(content.encode('utf-8')) > 1024 * 1024:
        raise ValueError('Expected manifest exceeds 1 MiB')
    if format == 'json':
        data = json.loads(content)
        if isinstance(data, dict):
            if data.get('schema_version') != 1 or set(data) - {'schema_version','files'}:
                raise ValueError('Expected manifest JSON requires schema_version 1 and files')
            data = data.get('files')
    elif format == 'csv':
        reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff'), newline=''))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError('Expected CSV requires unique column headers')
        if set(reader.fieldnames) - EXPECTED_FIELDS:
            raise ValueError('Unsupported expected CSV columns: ' + ', '.join(sorted(set(reader.fieldnames) - EXPECTED_FIELDS)))
        try:
            data = list(reader)
        except csv.Error as exc:
            raise ValueError('Invalid expected delivery CSV') from exc
    else:
        raise ValueError('Expected manifest format must be csv or json')
    if not isinstance(data, list) or len(data) > 500:
        raise ValueError('Expected manifest requires at most 500 file rows')
    rows = []
    for index, row in enumerate(data):
        if not isinstance(row, dict) or set(row) - EXPECTED_FIELDS:
            raise ValueError(f'Unsupported expected row {index + 1}')
        normalized = {}
        for key, value in row.items():
            if value is None or value == '':
                continue
            if key in {'expected_reads','expected_bases'}:
                if isinstance(value, str) and re.fullmatch(r'\d+', value.strip()):
                    value = int(value)
                if integer(value) is None:
                    raise ValueError('Expected reads/bases must be nonnegative safe integers, without scaling')
                value = int(value)
            elif not isinstance(value, str) or len(value) > (4096 if key == 'path' else 512):
                raise ValueError('Expected identity fields must be bounded text')
            normalized[key] = value
        if not any(key in normalized for key in ('file_id','path','filename')):
            raise ValueError('Each expected row needs file_id, exact path or filename')
        if 'read' in normalized and normalized['read'] not in {'R1','R2','SE','unpaired'}:
            raise ValueError('Expected read must be R1, R2, SE or unpaired')
        if 'sha256' in normalized:
            if not re.fullmatch('[a-fA-F0-9]{64}', normalized['sha256']):
                raise ValueError('Expected SHA-256 must have 64 hexadecimal characters')
            normalized['sha256'] = normalized['sha256'].lower()
        rows.append(normalized)
    return rows


def inventory(run, metrics, current):
    paths = run.get('sample_input_paths', run['inputs'])
    if run['mode'] == 'multiqc' and not run.get('sample_input_paths'):
        paths = []
    notices = []
    if len(set(paths)) != len(paths):
        notices.append({'code':'duplicate_input_reference','message':'Repeated exact input references were counted once; review the saved configuration'})
    paths = list(dict.fromkeys(paths))
    entries = plan([Path(path) for path in paths])
    scan = run.get('integrity', {})
    scans = {entry['path']:entry for entry in scan.get('files', [])}
    old = {entry['path']:entry for entry in run.get('input_metadata', [])}
    samples = metrics.get('samples', [])
    names = Counter(Path(path).name for path in paths)
    if any(count > 1 for count in names.values()):
        notices.append({'code':'duplicate_basename','message':'Distinct directories contain identical filenames. Use stable file IDs or scoped sample/lane identities in expectations'})
    result = []
    for planned in entries:
        path = planned['path']; observed = current.get(path, {})
        available = observed.get('snapshot') is not None and not observed.get('error')
        original = old.get(path)
        same_qc = bool(available and original and all(key in original for key in ('size','mtime_ns')) and all(observed['snapshot'].get(key) == original.get(key, observed['snapshot'].get(key)) for key in observed['snapshot']))
        scanned = scans.get(path)
        fresh = bool(available and scanned and scanned.get('state') == 'passed' and scanned.get('coverage') == 'full' and scanned.get('source_snapshot') == observed['snapshot'])
        scan_matches = bool(available and scanned and scanned.get('source_snapshot') == observed['snapshot'])
        matched = [sample for sample in samples if run.get('report_input_map', {}).get(sample['id'], {}).get('path') == path]
        if not matched and names[planned['name']] == 1:
            matched = [sample for sample in samples if sample['name'] == planned['name']]
        qc = matched[0] if len(matched) == 1 else None
        groups = [group for group in run.get('sample_groups', []) if path in group['files']]
        group = groups[0] if len(groups) == 1 else None
        pairing = next((entry for entry in run.get('input_pairing', []) if entry['path'] == path), {})
        if pairing.get('ambiguous') and pairing.get('source','auto') == 'auto':
            notices.append({'code':'ambiguous_pairing','file_id':planned['id'],'message':'Filename-based read relationship is ambiguous; no mate is inferred'})
        if pairing.get('read') in {'R1','R2'} and not pairing.get('paired'):
            notices.append({'code':'unpaired_read','file_id':planned['id'],'message':'Read-labelled file has no confirmed mate in this analysis; intentional unpaired analysis remains supported'})
        reads = integer(scanned['records_scanned']) if fresh else integer(qc.get('total_sequences')) if available and same_qc and qc and not (scan_matches and scanned.get('state') == 'failed') else None
        bases = integer(scanned['bases_scanned']) if fresh else None
        counts_source = 'full FASTQ scan' if fresh else 'FastQC reported read records' if reads is not None else 'not evaluated'
        length = qc.get('sequence_length','') if qc else ''
        if bases is None and reads is not None and re.fullmatch(r'\d+', length):
            bases = integer(reads * int(length))
            counts_source += '; bases = records × reported fixed length'
        result.append({'file_id':planned['id'],'path':path,'filename':planned['name'],
                       'input_reference':f"inputs/{planned['id']}/" + (re.sub(r'[^A-Za-z0-9._-]', '_', planned['name'])[:180] or 'reads.fastq'),
                       'sample_id':group['id'] if group else planned['id'], 'sample_name':group['display_name'] if group else planned['name'],
                       'group_source':group.get('source') if group else 'unassigned',
                       'lane':pairing.get('lane'),'chunk':pairing.get('chunk'),
                       'read':pairing.get('read') or ('SE' if pairing.get('assignment') == 'single' else 'unpaired'),
                       'pair_id':pairing.get('pair_key') if pairing.get('paired') else None,
                       'pair_source':pairing.get('source'), 'input_available':bool(available),
                       'availability_error':observed.get('error'), 'qc_snapshot_matches':same_qc if original else None,
                       'size_bytes':observed['snapshot']['size'] if available else original.get('size') if original else None,
                       'size_source':'current filesystem metadata' if available else 'saved QC input metadata' if original else 'unavailable',
                       'source_snapshot':observed.get('snapshot'), 'sequence_length':(str(scanned['min_length']) if scanned.get('min_length') == scanned.get('max_length') else f"{scanned['min_length']}-{scanned['max_length']}") if fresh and scanned.get('min_length') is not None else length if same_qc else None, 'reads':reads,'bases':bases,
                       'q20_bases':scanned.get('q20_bases') if fresh else None,
                       'q30_bases':scanned.get('q30_bases') if fresh else None,
                       'quality_bases':scanned.get('quality_bases') if fresh else None,
                       'encoding_source':scanned.get('encoding_source') if fresh else None,
                       'counts_source':counts_source, 'sha256':scanned.get('sha256') if fresh else None,
                       'checksum_status':scanned.get('checksum_status') if fresh else 'not_evaluated',
                       'integrity_state':scanned.get('state') if scan_matches or scanned and not available else 'stale' if scanned else 'not_evaluated',
                       'report_id':qc.get('id') if qc else None})
    for sample_id in dict.fromkeys(entry['sample_id'] for entry in result):
        rows = [entry for entry in result if entry['sample_id'] == sample_id]
        lanes = {int(entry['lane'][1:]) for entry in rows if entry['lane'] and re.fullmatch(r'L\d{3}',entry['lane'])}
        if len(lanes) > 1:
            missing = sorted(set(range(min(lanes),max(lanes)+1))-lanes)
            if missing:
                notices.append({'code':'observed_lane_gap','sample_id':sample_id,'message':'Not observed in selected files: ' + ', '.join(f'L{lane:03d}' for lane in missing) + '. Expected lanes have not been inferred'})
    return {'files':result,'notices':notices,'source_kind':'source_fastq' if paths else 'reports_only',
            'integrity_task_state':scan.get('state','not_evaluated'), 'integrity_result':scan.get('result','not_evaluated')}


def reconcile(files, expected):
    result = {'status':'not_evaluated','missing':[],'extra':[],'ambiguous':[],'duplicates':[],'mismatches':[],'unavailable':[],'matched':[]}
    if expected is None:
        result['message'] = 'No expected delivery manifest was supplied'
        return result
    if not files and not expected:
        result['message'] = 'No source FASTQ inventory is available for reconciliation'
        return result
    claimed, candidates_seen = set(), set()
    for index, row in enumerate(expected):
        candidates = files
        for expected_key, actual_key in [('file_id','file_id'),('path','path'),('filename','filename'),('sample_id','sample_id'),('sample_name','sample_name'),('lane','lane'),('chunk','chunk'),('read','read')]:
            if expected_key in row:
                candidates = [entry for entry in candidates if entry[actual_key] == row[expected_key]]
        candidates_seen.update(entry['file_id'] for entry in candidates)
        marker = {'expected_row':index+1, 'identity':{key:value for key,value in row.items() if key not in {'expected_reads','expected_bases','sha256'}}}
        if not candidates:
            result['missing'].append(marker);continue
        if len(candidates) > 1:
            result['ambiguous'].append({**marker,'file_ids':[entry['file_id'] for entry in candidates]});continue
        actual = candidates[0];marker['file_id'] = actual['file_id']
        if actual['file_id'] in claimed:
            result['duplicates'].append(marker);continue
        claimed.add(actual['file_id'])
        if not actual['input_available']:
            result['missing'].append(marker);continue
        result['matched'].append(marker)
        for key, metric in [('expected_reads','reads'),('expected_bases','bases'),('sha256','sha256')]:
            if key in row:
                if actual[metric] is None:
                    result['unavailable'].append({**marker,'metric':metric,'message':'Required observed value has not been measured reliably'})
                elif actual[metric] != row[key]:
                    result['mismatches'].append({**marker,'metric':metric,'expected':row[key],'observed':actual[metric]})
    result['extra'] = [entry['file_id'] for entry in files if entry['file_id'] not in candidates_seen]
    result['status'] = 'review_required' if any(result[key] for key in ('missing','extra','ambiguous','duplicates','mismatches')) else 'not_evaluated' if result['unavailable'] else 'matched'
    return result


def sum_known(rows, field):
    values = [row[field] for row in rows]
    return integer(sum(values)) if values and all(integer(value) is not None for value in values) else None


def yields(files, run, targets):
    output = []
    pair_evidence = {entry['id']:entry for entry in run.get('integrity',{}).get('pairs',[])}
    for sample_id in dict.fromkeys(entry['sample_id'] for entry in files):
        rows = [entry for entry in files if entry['sample_id'] == sample_id]
        totals = {key:sum_known(rows,key) for key in ('reads','bases','q20_bases','q30_bases','quality_bases')}
        pair_ids = {entry['pair_id'] for entry in rows if entry['pair_id']}
        pairs = 0 if pair_ids else None
        covered = set()
        for pair_id in pair_ids:
            members = [entry for entry in rows if entry['pair_id'] == pair_id]
            evidence = pair_evidence.get(pair_id, {})
            if len(members) != 2 or {entry['read'] for entry in members} != {'R1','R2'} or evidence.get('state') != 'passed' or any(entry['integrity_state'] != 'passed' for entry in members) or members[0]['reads'] != members[1]['reads'] or members[0]['reads'] is None:
                pairs = None;break
            covered.update(entry['file_id'] for entry in members)
            pairs += members[0]['reads']
        if len(covered) != len(rows):
            pairs = None
        totals['read_pairs'] = integer(pairs)
        denominator = totals['quality_bases']
        totals.update(q20_percent=100*totals['q20_bases']/denominator if denominator and totals['q20_bases'] is not None else None,
                      q30_percent=100*totals['q30_bases']/denominator if denominator and totals['q30_bases'] is not None else None)
        target = next((entry for entry in targets if entry['sample_id'] == sample_id), None)
        observed = totals.get(target['metric']) if target else None
        state = 'not_evaluated' if not target or observed is None else 'met' if observed >= target['minimum'] else 'below_target'
        output.append({'sample_id':sample_id,'sample_name':rows[0]['sample_name'],'file_ids':[entry['file_id'] for entry in rows],
                       'totals':totals, 'target':target, 'target_state':state,'observed':observed,
                       'denominator':'Read records/bases in selected source FASTQs; R1 and R2 are separate reads. Read pairs require complete synchronized mate evidence.',
                       'provenance':sorted({entry['counts_source'] for entry in rows}),
                       'explanation':'No quantity target configured' if not target else 'Required quantity is unavailable or incomparable' if observed is None else f"Observed {observed} {target['metric']} against explicit minimum {target['minimum']}"})
    return output


def export_data(data, include_paths=False):
    files = [{key:value for key,value in entry.items() if key not in {'path','availability_error','source_snapshot'}} for entry in data['files']]
    for row in files:
        # Historical automatic pair keys contain absolute directory paths. Keep
        # their relationship stable without leaking those paths into a handoff.
        if row.get('pair_id'):
            row['pair_id'] = 'pair:' + hashlib.sha256(row['pair_id'].encode()).hexdigest()[:24]
    if include_paths:
        for row, original in zip(files,data['files']):row['path'] = original['path']
    reconciliation = json.loads(json.dumps(data['reconciliation']))
    if not include_paths:
        for values in reconciliation.values():
            if isinstance(values,list):
                for entry in values:
                    if isinstance(entry,dict) and 'path' in entry.get('identity',{}):
                        path = entry['identity'].pop('path');entry['identity'].setdefault('filename',Path(path).name)
    return {'schema_version':1,'analysis_id':data['analysis_id'],'name':data['name'],'source_kind':data['source_kind'],
            'paths':'private absolute source paths included' if include_paths else 'relative references only; FASTQ files are not copied',
            'files':files,'notices':data['notices'],'reconciliation':reconciliation,'yields':data['yields'],
            'upstream_demultiplexing':{key:data.get('demultiplex',{}).get(key) for key in ('state','run_id','declared_run_id','reported_tool_version','declared_tool_version','version_source','reconciliation_state','lane_totals')} if data.get('demultiplex') else {'state':'not_evaluated'},
            'input_stage':data['input_stage'],'processing_notes':data['processing_notes'],'tool_versions':data['tool_versions']}


def csv_export(data, mode='spreadsheet', include_paths=False):
    fields = CSV_FIELDS + (['path'] if include_paths else [])
    stream = io.StringIO(newline='');writer = csv.writer(stream,lineterminator='\r\n',quoting=csv.QUOTE_ALL if mode == 'spreadsheet' else csv.QUOTE_MINIMAL)
    def cell(value):
        value = '' if value is None else str(value)
        first = value.lstrip()
        while first and unicodedata.category(first[0]) in {'Cc','Cf'}:first=first[1:].lstrip()
        numeric = re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',value)
        risky = value and (unicodedata.category(value[0]) in {'Cc','Cf'} or first.startswith(tuple('=+-@＝＋－＠')))
        return '\t'+value if mode == 'spreadsheet' and risky and not numeric else value
    writer.writerow(fields)
    for row in export_data(data,include_paths)['files']:
        writer.writerow([cell(row.get(field)) for field in fields])
    return stream.getvalue()


def expected_template(data):
    """Editable identities only. Measured inventory is not an independent contract."""
    return {'schema_version':1,'files':[{key:entry[key] for key in ('file_id','filename')}
                                      for entry in data['files']]}
