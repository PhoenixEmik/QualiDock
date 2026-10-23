"""Bounded local variant inputs and original BCFtools stats; no variant engine."""
import gzip
import os
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict
from .files import VARIANT
from .integrity import snapshot

HEADER_LIMIT = 4*1024*1024
LINE_LIMIT = 256*1024
MAX_SAMPLES = 10000
BGZF_EOF = bytes.fromhex('1f8b08040000000000ff0600424302001b0003000000000000000000')


class Options(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)
    per_sample: bool = False
    multiqc: bool = False


def readable(path):
    """Call only after FileAccess authorization; read at most a bounded header."""
    if not VARIANT.search(path.name) or '##idx##' in str(path) or any(ord(c)<32 for c in str(path)) or not path.is_file() or not path.stat().st_mode & 0o444 or not os.access(path,os.R_OK):
        raise ValueError('Choose a readable canonical .vcf, .vcf.gz or .bcf input without control characters or HTSlib index syntax')
    before=snapshot(path.stat())
    with path.open('rb') as raw:
        prefix=raw.read(18)
        compressed=prefix[:2]==b'\x1f\x8b'
        bgzf=compressed and len(prefix)==18 and prefix[3]&4 and prefix[12:16]==b'BC\x02\x00'
        if bgzf:
            if path.stat().st_size<28:raise ValueError('Truncated BGZF input')
            raw.seek(-28,2)
            if raw.read()!=BGZF_EOF:raise ValueError('BGZF EOF marker missing; incomplete input is not qualified')
    if path.name.lower().endswith('.vcf.gz') != compressed and not path.name.lower().endswith('.bcf'):
        raise ValueError('Variant compression does not match the file extension')
    if path.name.lower().endswith('.bcf') and compressed and not bgzf:
        raise ValueError('Compressed BCF requires the qualified BGZF format')
    try:
        with (gzip.open(path,'rb') if compressed else path.open('rb')) as stream:
            magic=stream.read(5)
            if path.name.lower().endswith('.bcf'):
                if magic!=b'BCF\x02\x02':raise ValueError('Only qualified BCF 2.2 is supported')
                length=stream.read(4)
                if len(length)!=4 or not 1<=int.from_bytes(length,'little')<=HEADER_LIMIT:raise ValueError('Invalid or oversized BCF header')
                text=stream.read(int.from_bytes(length,'little'))
                if len(text)!=int.from_bytes(length,'little') or not text.endswith(b'\x00'):raise ValueError('Truncated BCF header')
                lines=text[:-1].splitlines(keepends=True)
            else:
                lines=[];size=0;line=magic+stream.readline(LINE_LIMIT+1)
                while True:
                    size+=len(line)
                    if len(line)>LINE_LIMIT or size>HEADER_LIMIT:raise ValueError('VCF header exceeds 256 KiB per line /4 MiB')
                    lines.append(line)
                    if line.startswith(b'#CHROM\t'):break
                    if not line.startswith(b'##'):raise ValueError('Missing or invalid VCF column header')
                    line=stream.readline(LINE_LIMIT+1)
            decoded=[line.decode('utf-8').rstrip('\r\n') for line in lines]
    except (OSError,EOFError,UnicodeError) as exc:
        raise ValueError('Invalid or truncated variant header/compression') from exc
    if not decoded or decoded[0] not in {'##fileformat=VCFv4.2','##fileformat=VCFv4.3'}:
        raise ValueError('Only genuinely qualified VCF 4.2 /4.3 headers are supported')
    if any(len(line.encode('utf-8'))>LINE_LIMIT for line in decoded) or any(not line.startswith('##') for line in decoded[:-1]) or any(line.startswith('##fileformat=') for line in decoded[1:]):
        raise ValueError('Malformed or ambiguous variant header')
    columns=decoded[-1].split('\t')
    if columns[:8]!=['#CHROM','POS','ID','REF','ALT','QUAL','FILTER','INFO'] or (len(columns)!=8 and (len(columns)<10 or columns[8]!='FORMAT')):
        raise ValueError('Unsupported VCF columns')
    samples=columns[9:]
    if len(samples)>MAX_SAMPLES or len(set(samples))!=len(samples) or any(not s or len(s)>200 or any(c.isspace() or ord(c)<32 for c in s) for s in samples):
        raise ValueError('VCF requires unique nonempty sample IDs (at most 10000,200 characters each)')
    tags={kind:sorted({m[1] for line in decoded for m in [re.match(r'##'+kind+r'=<ID=([^,>]+),',line)] if m}) for kind in ['INFO','FORMAT']}
    if snapshot(path.stat())!=before:raise ValueError('Variant input changed during header checks')
    if not compressed and not path.name.lower().endswith('.bcf'):
        with path.open('rb') as stream:
            stream.seek(-1,2)
            if stream.read()!=b'\n':raise ValueError('Qualified text VCF requires a complete final newline')
    return {'format':'BCF 2.2' if path.name.lower().endswith('.bcf') else decoded[0].removeprefix('##fileformat='),
            'compression':'BGZF' if bgzf else 'gzip' if compressed else 'none','samples':samples,'tags':tags,'source_snapshot':before}
