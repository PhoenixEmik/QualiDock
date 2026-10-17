#!/usr/bin/env python3
"""Explicit FR/RF/TANDEM geometry, never invoked by the application."""
import argparse
from pathlib import Path
import subprocess


def prepare(directory, samtools='samtools', single=False, libraries=False):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    header='@HD\tVN:1.6\tSO:coordinate\n@SQ\tSN:chrDNA\tLN:10000\n@RG\tID:dna\tSM:fixture\tLB:library-A\tPL:ILLUMINA\n'
    if libraries:header+='@RG\tID:other\tSM:fixture\tLB:library-B\tPL:ILLUMINA\n'
    records=[]
    def pair(name,start,size,orientation,duplicate=False,rg='dna'):
        flags={'FR':(99,147),'RF':(83,163),'TANDEM':(67,131)}[orientation]
        second=start+size-50
        for flag,pos,mate,tlen in [(flags[0],start,second,size),(flags[1],second,start,-size)]:
            if duplicate:flag|=1024
            records.append((pos,f'{name}\t{flag}\tchrDNA\t{pos}\t60\t50M\t=\t{mate}\t{tlen}\t'+ 'A'*50+'\t'+'I'*50+'\tRG:Z:'+rg))
    if not single:
        for i,(size,orientation) in enumerate([(150,'FR'),(250,'FR'),(350,'FR'),(200,'RF'),(300,'RF'),(400,'TANDEM')]):
            pair('pair'+str(i),100+i*1000,size,orientation,rg='other' if libraries and i>=3 else 'dna')
        pair('duplicate',6500,150,'FR',True)
    records.append((8000,'single\t0\tchrDNA\t8000\t60\t50M\t*\t0\t0\t'+'A'*50+'\t'+'I'*50+'\tRG:Z:dna'))
    sam=directory/'input.sam';sam.write_text(header+'\n'.join(row for _,row in sorted(records))+'\n')
    bam=directory/'input.bam'
    subprocess.run([samtools,'view','-b','-o',str(bam),str(sam)],check=True,capture_output=True)
    return bam


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--single',action='store_true')
    args=parser.parse_args();prepare(args.output,single=args.single)
