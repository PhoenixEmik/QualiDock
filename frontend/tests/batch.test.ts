import assert from 'node:assert/strict';
import test from 'node:test';
import {addCohortId, batchActive, stageLabel} from '../src/batch.ts';

test('cohort uses explicit stable identities, distinct from display labels',()=>{
  const ids=['smp_same-name-1']; assert.deepEqual(addCohortId(ids,'smp_same-name-2'),[...ids,'smp_same-name-2']);
  assert.equal(addCohortId(ids,ids[0]),ids); assert.equal(addCohortId(ids,''),ids);
  assert.throws(()=>addCohortId(Array.from({length:100},(_,i)=>`smp_${i}`),'smp_new'),/at most 100/);
});
test('batch statuses preserve unknown, skipped, reuse and actual validation result',()=>{
  assert.equal(stageLabel({state:'not_evaluated'}),'not evaluated');
  assert.equal(stageLabel({state:'completed',reused:true,result:'passed'}),'completed · reused · passed');
  assert.equal(stageLabel({state:'completed',validation_result:'not_evaluated'}),'completed · target not evaluated');
  assert.equal(stageLabel({state:'skipped',reason:'not requested'}),'skipped');
  assert(batchActive('running')); assert(batchActive('queued'));
  for(const state of ['completed','failed','partial','cancelled','interrupted']) assert(!batchActive(state));
});
