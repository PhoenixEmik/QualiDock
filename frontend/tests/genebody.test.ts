import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import * as echarts from 'echarts';
import { geneBodyView } from '../src/geneBodyChart.ts';
const report = readFileSync(new URL('../../backend/tests/fixtures/rseqc-5.0.5/genebody/gene-body.geneBodyCoverage.txt', import.meta.url),'utf8').trim().split('\n').map(l=>l.split('\t'));
const rows = report[0].slice(1).map((p,i)=>[p,report[1][i+1]]);
test('genuine gene-body values retain 1–100 and raw maximum 2, without R normalization',()=>{
 const original=structuredClone(rows);const view=geneBodyView(rows,'source.bam');
 const series=(view.options.series as any[])[0];
 assert.equal(series.smooth,false);assert.equal(series.connectNulls,false);assert.equal(series.data.length,100);
 assert.deepEqual(series.data.map((d:any)=>d.raw),rows);
 assert.equal(Math.max(...series.data.map((d:any)=>d.value[1])),2);
 assert.deepEqual(rows,original);
 const format=(view.options.tooltip as any).formatter;
 assert.match(format([{data:series.data[0]}]),/5′ → 3′/);
 assert.match(format([{data:series.data[0]}]),/0\.0/);
 assert.ok(!series.markArea);
});
for (const width of [390,1400]) test(`gene-body chart renders finite responsive SVG at ${width}`,()=>{
 const c=echarts.init(null,undefined,{renderer:'svg',ssr:true,width,height:420});
 try {c.setOption(geneBodyView(rows,'file <unsafe>').options); const svg=c.renderToSVGString();assert.match(svg,/<svg/);assert.doesNotMatch(svg,/NaN|Infinity|<unsafe>/);}finally{c.dispose();}
});

test('shared series visibility actions actually hide and restore the gene-body curve',()=>{
 const c=echarts.init(null,undefined,{renderer:'svg',ssr:true,width:800,height:420});
 try {
  const view=geneBodyView(rows,'input.bam');c.setOption(view.options);
  const name=view.series[0].name;
  c.dispatchAction({type:'legendUnSelect',name});
  assert.equal((c.getOption().legend as any[])[0].selected[name],false);
  c.dispatchAction({type:'legendSelect',name});
  assert.equal((c.getOption().legend as any[])[0].selected[name],true);
 }finally{c.dispose();}
});
