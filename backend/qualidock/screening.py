"""Explicit offline Kraken2 evidence: counts are classifications, not conclusions."""
from decimal import Decimal,InvalidOperation
import os
from pathlib import Path
import re
import stat
from .integrity import snapshot
from .metrics import bounded_text

DB_FILES=('hash.k2d','opts.k2d','taxo.k2d')
COLUMNS=['Reported percent','Clade read records','Direct read records','Rank','Taxonomy ID','Reported taxon name']


def parse_text(text):
    rows=[];taxa=set();root=None;unclassified=None
    for line in text.splitlines():
        if not line:continue
        values=line.split('\t')
        if len(values)!=6 or len(rows)>=10000 or any(len(value)>4096 for value in values):raise ValueError('Unsupported/oversized Kraken2 six-column report')
        percent,clade,direct,rank,taxid,name=values
        try:amount=Decimal(percent.strip())
        except InvalidOperation as exc:raise ValueError('Invalid Kraken2 percentage') from exc
        if not amount.is_finite() or not 0<=amount<=100:raise ValueError('Invalid Kraken2 percentage')
        if any(not re.fullmatch(r'[0-9]+',value.strip()) or int(value)>2**53-1 for value in (clade,direct)) or not re.fullmatch('[0-9]+',taxid.strip()) or int(direct)>int(clade):raise ValueError('Invalid Kraken2 count/taxonomy identity')
        taxid=taxid.strip()
        if taxid in taxa:raise ValueError('Duplicate Kraken2 taxon row')
        taxa.add(taxid);row={'reported_percent':percent.strip(),'clade_reads':int(clade),'direct_reads':int(direct),'rank':rank,'taxid':taxid,'name':name,'raw':values};rows.append(row)
        if taxid=='1':
            if rank!='R':raise ValueError('Kraken2 root rank is unsupported')
            root=int(clade)
        if taxid=='0':
            if rank!='U':raise ValueError('Kraken2 unclassified rank is unsupported')
            unclassified=int(clade)
    if rows and root is None and unclassified is None:raise ValueError('Report lacks root/unclassified denominators')
    # Default Kraken2 reports omit zero-count taxa. An all-unclassified report
    # has no root, and a fully classified report may omit the U row. Empty text
    # alone does not establish zero input records.
    classified=(root or 0) if rows else None;unknown=(unclassified or 0) if rows else None
    total=classified+unknown if rows else None
    if total is not None and total>2**53-1:raise ValueError('Kraken2 denominator exceeds the exact supported integer range')
    return {'schema':'kraken2.standard-six-column.v1','columns':COLUMNS,'rows':rows,'records_processed':total,'classified_records':classified,'unclassified_records':unknown,
            'denominator':'One FASTQ per invocation; individual read records, not paired fragments. Clade rows overlap and must not be summed.'}


def parse_report(path):return parse_text(bounded_text(path))


def configurations(settings):
    entries=settings.screening_databases
    if settings.screening_error:raise ValueError(settings.screening_error)
    if not isinstance(entries,list) or len(entries)>20:raise ValueError('Configure at most 20 offline reference databases')
    seen=set();result=[]
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)-{'id','name','path','version','source','reference_taxids'}:raise ValueError('Unsupported screening database configuration')
        for key,limit in [('id',80),('name',200),('path',4096),('version',120),('source',2000)]:
            if not isinstance(entry.get(key),str) or not entry[key].strip() or len(entry[key])>limit:raise ValueError('Screening references need explicit ID, name, path, version and source provenance')
        if not re.fullmatch('[A-Za-z0-9_-]+',entry['id']) or entry['id'] in seen:raise ValueError('Screening database IDs must be unique portable identifiers')
        taxa=entry.get('reference_taxids',[])
        if not isinstance(taxa,list) or len(taxa)>1000 or any(not isinstance(value,str) or not re.fullmatch('[0-9]{1,20}',value) for value in taxa):raise ValueError('Declared reference taxonomy IDs must be bounded decimal strings')
        seen.add(entry['id']);result.append({**entry,'reference_taxids':taxa})
    return result


def resolve_database(config):
    raw=Path(config['path']).expanduser()
    if not raw.is_absolute():raise ValueError('Offline database requires an administrator-configured absolute location')
    root=raw.resolve(strict=True)
    if not root.is_dir():raise ValueError('Offline database directory is unavailable')
    files=[]
    for name in DB_FILES:
        path=root/name;info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.resolve()!=path or not info.st_mode&0o444 or not os.access(path,os.R_OK):raise ValueError('Offline reference requires readable regular files without symlinks')
        if not info.st_size or name=='opts.k2d' and info.st_size!=64:raise ValueError('Unsupported or empty Kraken2 database file (opts.k2d must be the verified 64-byte layout)')
        files.append({'name':name,'source':str(path),'snapshot':snapshot(info)})
    return root,files


def public_database(config):
    result={key:value for key,value in config.items() if key!='path'}
    if result['source'].startswith(('file://','/')):
        result['source']='Private reference origin (path omitted)';result['source_private']=True
    return result
