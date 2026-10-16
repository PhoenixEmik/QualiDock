import test from "node:test";
import assert from "node:assert/strict";
import { inspectorRequest } from "../src/inspector.ts";

test("bounded inspector sends only selected paths and exact dataset authorities", () => {
  const refs=[{run_id:"parent",dataset_id:"R1",path:"/derived/R1.fq.gz"},{run_id:"other",dataset_id:"secret",path:"/elsewhere.fq"}];
  assert.deepEqual(inspectorRequest(["/derived/R1.fq.gz"],refs,5,false),{paths:["/derived/R1.fq.gz"],input_datasets:[{run_id:"parent",dataset_id:"R1"}],count:5,paired:false});
  assert.equal(inspectorRequest(["/r1","/r2"],[],20,true).paired,true);
  for (const n of [0,21,1.5,NaN]) assert.throws(()=>inspectorRequest(["/r1"],[],n,false));
  for (const paths of [[],["/r1","/r1"],["/r1","/r2","/r3"]]) assert.throws(()=>inspectorRequest(paths,[],5,false));
  assert.throws(()=>inspectorRequest(["/r1"],[],5,true));
});
