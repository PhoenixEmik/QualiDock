#!/usr/bin/env python3
"""Explicit synthetic variant geometry; conversions occur in tests only."""
import argparse
import gzip
from pathlib import Path
import subprocess

BASE = '##fileformat=VCFv4.3\n##contig=<ID=chr1,length=1000>\n##contig=<ID=chr2,length=1000>\n'
COLS = '#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO'
SAMPLES = '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n'
DEPTH = '##INFO=<ID=DP,Number=1,Type=Integer,Description="Site depth">\n##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Sample depth">\n'
COUNTS = '##INFO=<ID=AC,Number=A,Type=Integer,Description="Alternate allele count">\n##INFO=<ID=AN,Number=1,Type=Integer,Description="Called allele count">\n'
END = '##INFO=<ID=END,Number=1,Type=Integer,Description="End coordinate">\n'

CASES = {
    'snps': (BASE, COLS, ['chr1\t10\t.\tA\tG\t50\tPASS\t.', 'chr1\t20\t.\tC\tA\t30\tPASS\t.']),
    'indels': (BASE, COLS, ['chr1\t10\t.\tA\tAT\t40\tPASS\t.', 'chr1\t20\t.\tAT\tA\t60\tPASS\t.']),
    'mixed': (BASE+END, COLS, ['chr1\t10\t.\tA\tG\t50\tPASS\t.', 'chr1\t20\t.\tA\tAT\t40\tPASS\t.', 'chr1\t30\t.\tAC\tGT\t60\tPASS\t.', 'chr1\t40\t.\tA\tG,AT\t70\tPASS\t.', 'chr1\t50\t.\tN\t<DEL>\t.\tPASS\tEND=60', 'chr1\t70\t.\tA\t.\t.\tPASS\t.']),
    'multisample': (BASE+SAMPLES+DEPTH+COUNTS, COLS+'\tFORMAT\talpha\tbeta', ['chr1\t10\t.\tA\tG\t50\tPASS\tAC=1;AN=4;DP=22\tGT:DP\t0/1:10\t0/0:12', 'chr1\t20\t.\tC\tA\t30\tPASS\tAC=3;AN=4;DP=18\tGT:DP\t1/1:8\t0/1:10', 'chr1\t30\t.\tA\tAT\t40\tPASS\tAC=1;AN=2;DP=7\tGT:DP\t./.:.\t0/1:7', 'chr1\t40\t.\tA\tC,G\t60\tPASS\tAC=1,1;AN=4;DP=20\tGT:DP\t1/2:9\t0/0:11']),
    'missing-depth': (BASE+SAMPLES, COLS+'\tFORMAT\talpha\tbeta', ['chr1\t10\t.\tA\tG\t.\tPASS\t.\tGT\t0/1\t./.', 'chr1\t20\t.\tC\tA\t.\tPASS\t.\tGT\t./.\t./.']),
    'no-genotype': (BASE+'##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="Genotype quality">\n', COLS+'\tFORMAT\talpha', ['chr1\t10\t.\tA\tG\t.\tPASS\t.\tGQ\t20']),
    'missing-alleles': (BASE, COLS, ['chr1\t10\t.\tA\t.\t.\tPASS\t.', 'chr1\t20\t.\tC\tC\t.\tPASS\t.']),
    'symbolic': (BASE+END, COLS, ['chr1\t10\t.\tN\t<DEL>\t.\tPASS\tEND=30', 'chr1\t40\t.\tN\tN]chr2:321]\t.\tPASS\t.', 'chr1\t60\t.\tA\t*\t.\tPASS\t.']),
    'gvcf': (BASE+SAMPLES+DEPTH+END, COLS+'\tFORMAT\talpha', ['chr1\t1\t.\tA\t<NON_REF>\t.\tPASS\tEND=20\tGT:DP\t0/0:10', 'chr1\t21\t.\tA\tG,<NON_REF>\t50\tPASS\tDP=5\tGT:DP\t0/1:5']),
    'empty': (BASE, COLS, []),
}


def prepare(directory, bcftools):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    result={}
    for name,(metadata,columns,rows) in CASES.items():
        source=directory/(name+'.vcf');source.write_text(metadata+columns+'\n'+''.join(row+'\n' for row in rows))
        result[name]=source
    older=directory/'snps-v42.vcf';older.write_text(result['snps'].read_text().replace('VCFv4.3','VCFv4.2'))
    result['vcf42']=older
    mixed=result['mixed']
    compressed=directory/'mixed.vcf.gz'
    with gzip.open(compressed,'wb') as stream:stream.write(mixed.read_bytes())
    result['gzip']=compressed
    for name,args in [('bgzf',['-Oz']),('bcf',['-Ob']),('uncompressed-bcf',['-Ou'])]:
        target=directory/('mixed.bgzf.vcf.gz' if name=='bgzf' else name+'.bcf')
        subprocess.run([bcftools,'view',*args,'--no-version','-o',str(target),str(mixed)],check=True,capture_output=True)
        result[name]=target
    raw=directory/'raw-bcf.bcf';raw.write_bytes(gzip.decompress(result['bcf'].read_bytes()));result['raw-bcf']=raw
    for name,args in [('multisample-bcf',['-Ob']),('multisample-bgzf',['-Oz'])]:
        target=directory/(name+('.bcf' if name.endswith('bcf') else '.vcf.gz'))
        subprocess.run([bcftools,'view',*args,'--no-version','-o',str(target),str(result['multisample'])],check=True,capture_output=True)
        result[name]=target
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--bcftools',required=True)
    args=parser.parse_args();prepare(args.output,args.bcftools)
