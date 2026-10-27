import test from 'node:test';
import assert from 'node:assert/strict';
import { hubSnapshot, clampHubPosition, readHubPosition, relativeHubPosition, absoluteHubPosition } from '../web/floating-hub.js';

const job = (id, fields = {}) => ({ id, status: 'rendering', kind: 'export', progress: null, created: '2026-10-23T08:00:00Z', ...fields });

test('unknown progress stays unknown, finite 0 is determinate and bounds are enforced', () => {
  for (const progress of [null, undefined, '', '30', NaN, Infinity, -Infinity, false]) assert.equal(hubSnapshot([job('a', { progress })]).selected.progress, null);
  for (const [progress, expected] of [[0, 0], [25.4, 25.4], [-1, 0], [101, 100]]) assert.equal(hubSnapshot([job('a', { progress })]).selected.progress, expected);
});

test('real selected task progress is preserved instead of averaging different jobs', () => {
  const jobs = [job('old', { progress: 90 }), job('new', { progress: null, created: '2026-10-23T09:00:00Z' }), job('done', { status: 'completed', created: '2026-10-23T10:00:00Z' })];
  const before = JSON.stringify(jobs), snapshot = hubSnapshot(jobs);
  assert.equal(snapshot.activeCount, 2); assert.equal(snapshot.selected.id, 'new'); assert.equal(snapshot.selected.progress, null);
  assert.deepEqual(snapshot.rows.map((entry) => entry.id), ['new', 'old', 'done']);
  assert.equal(JSON.stringify(jobs), before);
});

test('all jobs count but task rows stay bounded and cancellation is not treated as complete', () => {
  const snapshot = hubSnapshot(Array.from({ length: 8 }, (_, i) => job(`j${i}`, { created: i, status: i === 7 ? 'cancelling' : 'completed' })));
  assert.equal(snapshot.total, 8); assert.equal(snapshot.rows.length, 3); assert.equal(snapshot.activeCount, 1);
  assert.equal(snapshot.selected.id, 'j7'); assert.equal(snapshot.selected.stage, '正在取消');
  assert.equal(hubSnapshot([job('j', { status: 'needs_input' })]).activeCount, 0);
});

test('bad identities and duplicate IDs are ignored without permitting unsafe actions', () => {
  const snapshot = hubSnapshot([null, job('../path'), job('<img>'), job('safe', { project_id: '../../unsafe' }), job('safe'), job('valid', { project_id: 'p_123-abc', status: 'constructor' })]);
  assert.equal(snapshot.total, 2); assert.equal(snapshot.rows[0].projectId, null);
  assert.equal(snapshot.rows[1].projectId, 'p_123-abc'); assert.equal(snapshot.rows[1].status, 'unknown');
  assert.equal(hubSnapshot([job('stage', { stage: 'constructor' })]).selected.stage, 'constructor');
  assert.deepEqual(hubSnapshot({}), { total: 0, activeCount: 0, selected: null, rows: [] });
});

test('saved position parsing tolerates denied/corrupt/old storage and requires finite coordinates', () => {
  for (const raw of [null, '', '{broken', 'null', '{}', '{"v":1,"x":"10","y":20}', '{"v":1,"x":1e999,"y":0}', '{"v":2,"x":1,"y":2}']) assert.equal(readHubPosition(raw), null);
  assert.deepEqual(readHubPosition('{"v":1,"x":-100,"y":20000}'), { x: -100, y: 20000 });
});

test('positions clamp to small mobile and offset visual viewports after resize', () => {
  assert.deepEqual(clampHubPosition({ x: -20, y: 900 }, { width: 390, height: 700 }, 60), { x: 12, y: 628 });
  assert.deepEqual(clampHubPosition({ x: 1000, y: 1000 }, { left: 70, top: 30, width: 240, height: 210 }, 60), { x: 238, y: 168 });
  assert.deepEqual(clampHubPosition(null, { width: 390, height: 700 }, 60), { x: 318, y: 556 });
  assert.deepEqual(clampHubPosition({ x: NaN, y: Infinity }, { width: 50, height: 40 }, 60), { x: 0, y: 0 });
});

test('normalized positions round-trip and preserve relative placement across viewports',()=>{
  const desktop={width:1440,height:960},mobile={left:20,top:30,width:320,height:500};
  const relative=relativeHubPosition({x:700,y:450},desktop,64),position=absoluteHubPosition(relative,desktop,64);
  assert.ok(Math.abs(position.x-700)<.001);assert.ok(Math.abs(position.y-450)<.001);
  const moved=absoluteHubPosition(relative,mobile,64),restored=relativeHubPosition(moved,mobile,64);
  assert.ok(Math.abs(restored.x-relative.x)<.001);assert.ok(Math.abs(restored.y-relative.y)<.001);
  assert.deepEqual(absoluteHubPosition({x:0,y:1},mobile,64),{x:32,y:454});
});
