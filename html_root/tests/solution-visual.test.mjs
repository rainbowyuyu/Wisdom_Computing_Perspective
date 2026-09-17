import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visualMarkup } from '../static/js/solution-visual.js';

test('geometry draws independent edges without joining unrelated marked points', () => {
  const visual = {kind:'geometry', points:[[0,0],[4,0],[1,3],[2.5,1.5]], labels:['A','B','C','D'], segments:[[0,1],[1,2],[2,0],[0,3]]};
  const html = visualMarkup(visual);
  const lines = [...html.matchAll(/<polyline points="([^"]+)"/g)];
  assert.equal(lines.length, 4);
  assert.ok(lines.every(line => line[1].split(' ').length === 2));
  assert.equal(lines[0][1].split(' ')[0], lines[3][1].split(' ')[0]);
  const half = visualMarkup(visual,.5).match(/<polyline points="([^"]+)"/)[1];
  const [start,end] = lines[0][1].split(' ').map(p=>p.split(',').map(Number));
  const halfway = half.split(' ')[1].split(',').map(Number);
  assert.ok(Math.abs(halfway[0]-(start[0]+end[0])/2)<.02);
  assert.equal(halfway[1],start[1]);
  assert.equal((visualMarkup({...visual, segments:[]}).match(/<polyline/g) || []).length, 0);
  assert.equal((visualMarkup({...visual, segments:undefined}).match(/<polyline/g) || []).length, 1);
});
