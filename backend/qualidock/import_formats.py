"""Small explicit QC-report allowlist, not an execution or plugin interface."""
import json
import math
from .metrics import bounded_text


def fastp_metadata(path):
    def constant(value):
        raise ValueError('Non-finite values are unsupported in fastp JSON')
    def finite(value):
        number = float(value)
        if not math.isfinite(number):raise ValueError("Non-finite fastp JSON number")
        return number
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result:
                raise ValueError('Duplicate fastp JSON object field')
            result[key] = value
        return result
    data = json.loads(bounded_text(path),parse_constant=constant,parse_float=finite,object_pairs_hook=unique)
    summary = data.get('summary') if isinstance(data,dict) else None
    if not isinstance(summary,dict) or 'fasterp_version' in summary:
        raise ValueError('Unsupported QC JSON: expected fastp summary schema')
    for stage in ('before_filtering','after_filtering'):
        row = summary.get(stage)
        if not isinstance(row,dict) or any(not isinstance(row.get(key),int) or isinstance(row[key],bool) or row[key]<0 for key in ('total_reads','total_bases')):
            raise ValueError('Unsupported fastp JSON: expected before/after filtering integer read/base counts')
    if not isinstance(data.get('command'),str) or not isinstance(data.get('read1_before_filtering'),dict):
        raise ValueError('Unsupported fastp JSON: command and read1_before_filtering are required')
    version = summary.get('fastp_version')
    if version is not None and (not isinstance(version,str) or len(version)>100):
        raise ValueError('Invalid reported fastp version')
    return {'kind':'fastp','tool':'fastp','version':version,'schema':'fastp.before_after.v1',
            'before_filtering':summary['before_filtering'],'after_filtering':summary['after_filtering']}


def source_mappings(path):
    """Verified MultiQC 1.x module → section → sample → source-path schema.

    Unknown structures remain unmapped; never derive FASTQ identities from a
    fastp command string or merge reports by similar sample names.
    """
    data = json.loads(bounded_text(path))
    sources = data.get('report_data_sources',{}) if isinstance(data,dict) else {}
    result = {}
    if not isinstance(sources,dict):return result
    for module,sections in sources.items():
        if module.lower() not in {'fastqc','fastp','fastq screen','samtools','rseqc','picard'} or not isinstance(sections,dict):continue
        for section,rows in sections.items():
            if module.lower() == 'samtools' and section not in {'stats','flagstat'}:continue
            if module.lower() == 'rseqc' and section not in {'infer_experiment','read_distribution','gene_body_coverage'}:continue
            if module.lower() == 'picard' and section not in {'InsertSizeMetrics','RnaSeqMetrics'}:continue
            if not isinstance(rows,dict):continue
            for name,source in rows.items():
                if isinstance(name,str) and isinstance(source,str):
                    result.setdefault(source,set()).add(name)
    return result
