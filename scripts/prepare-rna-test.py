#!/usr/bin/env python3
"""Explicit synthetic RNA alignment geometry, for real upstream-tool tests only."""
import argparse
from pathlib import Path
import subprocess


def prepare(directory, samtools='samtools', population='mixed', single=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    annotation = directory/'genes.bed12'
    annotation.write_text(
        'chrRNA\t1000\t5000\tplus\t0\t+\t1500\t4500\t0\t2\t1000,1000,\t0,3000,\n'
        'chrRNA\t10000\t14000\tminus\t0\t-\t10500\t13500\t0\t2\t1000,1000,\t0,3000,\n'
        'chrRNA\t20000\t24000\tambiguous-plus\t0\t+\t20500\t23500\t0\t2\t1000,1000,\t0,3000,\n'
        'chrRNA\t20000\t24000\tambiguous-minus\t0\t-\t20500\t23500\t0\t2\t1000,1000,\t0,3000,\n')
    records = []
    def pair(name, first, second, reverse=False, cigar='50M', length=50):
        span = max(first+length, second+50)-min(first,second)
        for flag,pos,mate,tlen,cig,n in [(83 if reverse else 99,first,second,span if first<second else -span,cigar,length),
                                      (163 if reverse else 147,second,first,span if second<first else -span,'50M',50)]:
            if single:flag,pos,mate,tlen = flag & 16,pos,0,0
            records.append((pos, f'{name}\t{flag}\tchrRNA\t{pos}\t60\t{cig}\t{"*" if single else "="}\t{mate}\t{tlen}\t'+ 'A'*n+'\t'+'I'*n+'\tRG:Z:rna'))
    if population == 'unstranded':
        pair('forward',1601,1701);pair('reverse',1801,1701,True)
    else:
        pair('forward',1601,1701)
        pair('minus',11601,11501,True)
        pair('spliced',1951,4101,cigar='50M2000N50M',length=100)
        if population == 'mixed':
            pair('reverse',1801,1701,True)
            pair('ambiguous',21601,21701)
    sam = directory/'input.sam'
    sam.write_text('@HD\tVN:1.6\tSO:coordinate\n@SQ\tSN:chrRNA\tLN:30000\n@RG\tID:rna\tSM:fixture\tLB:RNA\tPL:ILLUMINA\n'+
                   '\n'.join(row for _,row in sorted(records))+'\n')
    bam = directory/'input.bam'
    subprocess.run([samtools,'view','-b','-o',str(bam),str(sam)],check=True,capture_output=True)
    return bam,annotation


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samtools', default='samtools')
    args = parser.parse_args()
    prepare(args.output,args.samtools)
