import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import * as echarts from 'echarts';
import { picardRnaView } from '../src/geneBodyChart.ts';

const original=readFileSync(new URL('../../backend/tests/fixtures/picard-3.5.0/rna/bias-plus-NONE.rna_metrics.txt',import.meta.url),'utf8');
const rows=original.split('normalized_position\tAll_Reads.normalized_coverage\n')[1].trim().split('\n').map(l=>l.split('\t'));
test('Picard original 0–100 profile and raw precision are independent from RSeQC',()=>{
 const view=picardRnaView(rows,'source.bam'), series=(view.options.series as any[])[0];
 assert.equal(series.data.length,101);
 assert.deepEqual(series.data.map((d:any)=>d.raw),rows);
 assert.deepEqual(series.data.map((d:any)=>d.value[0]),Array.from({length:101},(_,i)=>i));
 assert.equal(series.smooth,false);assert.equal(series.connectNulls,false);
 assert.match((view.options.tooltip as any).formatter([{data:series.data[0]}]),new RegExp(rows[0][1]));
 assert.equal((view.options.xAxis as any).min,0);assert.equal((view.options.xAxis as any).max,100);
 assert.match(view.summary,/not absolute depth/);
});
for (const width of [390,1400]) test('Picard RNA finite responsive chart '+width,()=>{
 const c=echarts.init(null,undefined,{renderer:'svg',ssr:true,width,height:420});
 try{c.setOption(picardRnaView(rows,'<unsafe>').options);const svg=c.renderToSVGString();assert.match(svg,/<svg/);assert.doesNotMatch(svg,/NaN|Infinity|<unsafe>/);}finally{c.dispose();}
});
test('unavailable coverage is not expanded into a default-zero curve',()=>{
 assert.deepEqual(((picardRnaView([],'empty').options.series as any[])[0]).data,[]);
});
