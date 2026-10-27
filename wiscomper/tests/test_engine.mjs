import test from 'node:test';
import assert from 'node:assert/strict';
import {sampleObject, compileFrames, partialPath} from '../web/engine.js';

test('seeking a sparse keyframe track is absolute and retains omitted fields', () => {
  const object = {x: -5, y: 2, frames: [{t: 1, x: 0}, {t: 3, y: 6}, {t: 5, x: 8}]};
  const frames = compileFrames(object);
  assert.equal(sampleObject(object, .5, frames).x, -5);
  assert.equal(sampleObject(object, 2, frames).x, 0);
  assert.equal(sampleObject(object, 2, frames).y, 4);
  const first = sampleObject(object, 4, frames);
  sampleObject(object, 5, frames);
  assert.deepEqual(sampleObject(object, 4, frames), first);
  assert.equal(first.x, 4);
  assert.equal(first.y, 6);
});

test('draw fraction follows geometric length rather than vertex count', () => {
  const points = [[0, 0], [1, 0], [1, 3]];
  assert.deepEqual(partialPath(points, .5), [[0, 0], [1, 0], [1, 1]]);
  assert.deepEqual(partialPath(points, 0), []);
  assert.deepEqual(partialPath(points, 1), points);
  assert.deepEqual(partialPath([[0,0,0], [0,0,4]], .25), [[0,0,0], [0,0,1]]);
});

test('frame zero and endpoint preserve exact declared state', () => {
  const object = {frames: [{t:0, x:-2, scale:.5, opacity:0, draw:0}, {t:6,x:3,opacity:1,draw:1}]};
  assert.equal(sampleObject(object, 0).opacity, 0);
  const end = sampleObject(object, 100);
  assert.equal(end.x, 3); assert.equal(end.scale, .5); assert.equal(end.draw, 1);
});
