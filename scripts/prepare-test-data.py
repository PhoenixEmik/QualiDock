#!/usr/bin/env python3
"""Prepare explicitly synthetic UI scenarios and optional pinned public FASTQs.

This development utility never runs preprocessing or changes existing inputs.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import random
import urllib.request


SOURCE = Path(__file__).with_name('test-data-sources.json')
ADAPTER = 'AGATCGGAAGAGCACACGTCTGAACTCCAGTCA'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    """Idempotent, exclusive creation: different existing bytes are an error."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f'Refusing symlink destination: {path}')
    if path.exists():
        if digest(path.read_bytes()) != digest(data):
            raise ValueError(f'Existing file differs; choose a new output directory: {path}')
    else:
        with path.open('xb') as stream:
            stream.write(data)


def synthetic_fastq(sample, read, count, profile, seed):
    rng = random.Random(seed)
    output = io.BytesIO()
    repeated = ''.join(rng.choices('ACGT', k=150))
    with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as gz:
        for index in range(count):
            length = rng.choice([75, 100, 125, 150]) if profile == 'gc_n_duplication' else 150
            weights = [1, 4, 4, 1] if profile == 'gc_n_duplication' else None
            sequence = ''.join(rng.choices('ACGT', weights=weights, k=length))
            quality = [rng.randint(32, 40) for _ in range(length)]
            if profile == 'tail_drop':
                quality[-45:] = [rng.randint(5, 18 if read == 2 else 23) for _ in range(45)]
            elif profile == 'adapter_rich' and index % 3 == 0:
                sequence = sequence[:-len(ADAPTER)] + ADAPTER
            elif profile == 'gc_n_duplication':
                if index % 2 == 0:
                    sequence = repeated[:length]
                if index % 5 == 0:
                    sequence = sequence[:20] + 'NNNNNNNNNN' + sequence[30:]
            text = f'@SYNTHETIC:{sample}:{index}/{read}\n{sequence}\n+\n' + ''.join(chr(q + 33) for q in quality) + '\n'
            gz.write(text.encode('ascii'))
    return output.getvalue()


def scenarios():
    files = []
    def add(folder, name, sample, read=1, profile='reference'):
        files.append((f'{folder}/{name}.fastq.gz', sample, read, profile))
    for sample in ('C15', 'D20'):
        for lane in ('L001', 'L002', 'L003'):
            for read in (1, 2):
                add('synthetic-multilane', f'{sample}_S1_{lane}_R{read}_001', f'{sample}:{lane}:001', read)
    for read in (1, 2):
        add('synthetic-multilane', f'C15_S1_L001_R{read}_002', 'C15:L001:002', read)
    for profile in ('reference', 'tail_drop', 'adapter_rich', 'gc_n_duplication'):
        for read in (1, 2):
            add('synthetic-qc-profiles', f'{profile}_R{read}_001', profile, read, profile)
    add('synthetic-manual-pairing', 'facility forward reads', 'manual-pair', 1)
    add('synthetic-manual-pairing', 'facility reverse reads', 'manual-pair', 2)
    for name, read in [('missing_mate_R1_001', 1), ('single_end', 1), ('ambiguous_R1_001', 1), ('ambiguous_1_001', 1), ('ambiguous_R2_001', 2)]:
        add('synthetic-pairing-edges', name, name, read)
    for sample in range(1, 13):
        for read in (1, 2):
            profile = ('reference', 'tail_drop', 'adapter_rich', 'gc_n_duplication')[(sample - 1) % 4]
            add('synthetic-cohort', f'cohort_{sample:02d}_R{read}_001', f'cohort:{sample}', read, profile)
    return files


def fetch(url, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'QualiDock-test-data'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'Download exceeded size limit: {url}')
    return data


def public_files(output, folder, source, download, kind='public-upstream-subset'):
    """Preserve upstream bytes and verify pinned sizes/checksums, also on reuse."""
    records = []
    for item in source['files']:
        target = output / folder / item['name']
        if target.is_symlink():
            raise ValueError(f'Refusing symlink destination: {target}')
        if not download and not target.exists():
            continue
        url = f"https://raw.githubusercontent.com/{source['repository']}/{source['commit']}/{item['path']}"
        data = target.read_bytes() if target.exists() else fetch(url, item['size'])
        if len(data) != item['size'] or digest(data) != item['sha256']:
            raise ValueError(f'Public input checksum mismatch: {item["name"]}')
        save(target, data)
        records.append({**item, 'path': folder + '/' + item['name'], 'kind': kind, 'url': url,
                        'repository': source['repository'], 'commit': source['commit']})
    if download and records:
        for name in ('README.md', 'LICENSE'):
            target = output / folder / ('UPSTREAM-' + name)
            if not target.exists():
                save(target, fetch(f"https://raw.githubusercontent.com/{source['repository']}/{source['commit']}/{name}", 128 * 1024))
    return records


def prepare(output, count, download, extra=False):
    output = output.expanduser().absolute()
    sources = json.loads(SOURCE.read_text())
    records = []
    for relative, sample, read, profile in scenarios():
        seed = int(digest(f'{relative}:qualidock-v1'.encode())[:16], 16)
        data = synthetic_fastq(sample, read, count, profile, seed)
        save(output / relative, data)
        records.append({'path': relative, 'kind': 'synthetic', 'reads': count, 'profile': profile, 'sha256': digest(data), 'bytes': len(data)})
    records.extend(public_files(output, 'public-yeast-rnaseq', sources, download))
    for dataset in sources.get('additional_datasets', []):
        records.extend(public_files(output, dataset['folder'], dataset, extra, dataset['kind']))
    guide = '''# QualiDock test inputs

Synthetic folders contain generated reads, not biological samples. File naming,
lane labels and QC stress profiles exist only to exercise the UI and real tools.
No QC status is preassigned: inspect actual FastQC/MultiQC results.

- synthetic-multilane: C15 (3 lanes, one extra chunk), D20 (3 lanes); 14 files.
- synthetic-qc-profiles: reference, low-quality tails, adapter-rich reads,
  GC/N/duplication stress; 8 files. These are test patterns, not biological models.
- synthetic-manual-pairing: manually assign forward reads as R1 and reverse as R2.
- synthetic-pairing-edges: single-end, missing mate, and ambiguous R1 naming;
  ambiguous files must not auto-pair.
- synthetic-cohort: 12 independent artificial pairs / 24 files for native analytics.
- public-yeast-rnaseq (optional): unchanged nf-core subsets of SRR6357070,
  SRR6357071 and SRR6357076, 50,000 reads per file. See upstream documentation.

Generate analyses separately for each folder. Browse Files to select individual
reads, or Samples to select complete lane groups. Start FastQC + MultiQC normally.
Select the public folder for comparisons using observed experimental read data.
The upstream public subsets were already filtered/subsampled; they do not represent
the original full runs or unbiased library-wide QC. Synthetic lane groups are not
replicates of the public accessions. Never treat either as production study data.

All generated files and downloads stay under example-data (ignored by git).
manifest.json records checksums, origins and synthetic profiles. Existing files
with different bytes are never overwritten. Recreate a suite with different read
counts in a new directory. No tools are installed and no preprocessing is run.
'''
    save(output / 'README.md', guide.encode())
    manifest = {'schema_version': 1, 'synthetic_reads_per_file': count, 'public_source': sources, 'files': records}
    # The manifest can gain verified public entries on a subsequent download run.
    path = output / 'manifest.json'
    if path.is_symlink():
        raise ValueError('Refusing symlink manifest')
    temporary = output / '.manifest.json.new'
    save(temporary, (json.dumps(manifest, indent=2) + '\n').encode())
    temporary.replace(path)
    print(f'Prepared {len(records)} FASTQs ({sum(r["bytes"] if "bytes" in r else r["size"] for r in records):,} compressed bytes) in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('example-data/testing'))
    parser.add_argument('--reads', type=int, default=2000)
    parser.add_argument('--download-public', action='store_true', help='Fetch six pinned, checksum-verified yeast RNA-seq FASTQs (~13 MB)')
    parser.add_argument('--download-extra', action='store_true', help='Fetch eight additional pinned FASTQs: amplicon, small RNA, ONT and simulated bacterial reads (~42 MB); see docs/TEST-DATA.md')
    args = parser.parse_args()
    if not 1 <= args.reads <= 100000:
        parser.error('--reads must be between 1 and 100000')
    prepare(args.output, args.reads, args.download_public, args.download_extra)
