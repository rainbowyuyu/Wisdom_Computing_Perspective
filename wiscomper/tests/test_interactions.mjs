import test from 'node:test';
import assert from 'node:assert/strict';
import {sampleObject} from '../web/engine.js';
import {interactionDefaults, updateInteractionValues, dragValue, interactionOffsets, applyInteractionOffsets, normalizeView} from '../web/interactions.js';

const control = (id, property, multiplier = 1) => ({id, value: 0, min: -10, max: 10, step: .1, bindings: [{target_id: 'part', property, multiplier}], drag: {target_id: 'part', axis: 'horizontal', sensitivity: .02}});

test('accepted values are bounded, defaults stay exact, and undeclared/nonfinite values are ignored', () => {
  const controls = [{...control('turn', 'rotation'), value: .03}];
  const defaults = interactionDefaults(controls);
  assert.deepEqual(defaults, {turn: .03});
  assert.deepEqual(updateInteractionValues(controls, defaults, {turn: 80, injected: 1}), {turn: 10});
  for (const value of [NaN, Infinity, '2', null]) assert.deepEqual(updateInteractionValues(controls, defaults, {turn: value}), defaults);
  assert.deepEqual(updateInteractionValues(controls, defaults, {turn: .056}), {turn: .056});
});

test('absolute sampling adds controls together before clipping and never mutates the source', () => {
  const controls = [control('first', 'opacity'), control('second', 'opacity', -1), control('angle', 'rotation_y', 2)];
  const object = {opacity: .5, rotation_y: .2, frames: [{t: 0, x: 0}, {t: 6, x: 6}]};
  const snapshot = JSON.stringify(object), values = {first: 1, second: 1, angle: .4};
  const offsets = interactionOffsets(controls, values);
  const result = applyInteractionOffsets(sampleObject(object, 3), offsets.get('part'));
  assert.equal(result.opacity, .5); assert.equal(result.rotation_y, 1); assert.equal(result.x, 3);
  assert.equal(JSON.stringify(object), snapshot);
  assert.deepEqual(applyInteractionOffsets(sampleObject(object, 3), interactionOffsets([...controls].reverse(), values).get('part')), result);
  assert.equal(applyInteractionOffsets(sampleObject(object, 3), {scale: -20, opacity: 100, draw: -1, x: 20000}).scale, .01);
  assert.equal(applyInteractionOffsets(sampleObject(object, 3), {opacity: 100}).opacity, 1);
  assert.equal(applyInteractionOffsets(sampleObject(object, 3), {x: 20000}).x, 10000);
});

test('drag snaps positive and negative CSS movement, clamps endpoints, and ignores executable fields', () => {
  const c = {...control('x', 'x'), min: -1, max: 1, step: .1};
  assert.equal(dragValue(c, 0, 13), .3);
  assert.equal(dragValue(c, 0, -13), -.3);
  assert.equal(dragValue(c, 0, 1000), 1);
  assert.equal(dragValue(c, 0, -1000), -1);
  c.bindings.push({target_id: 'part', property: 'latex', multiplier: 1}, {target_id: 'part', property: '__proto__', multiplier: 1});
  assert.deepEqual(interactionOffsets([c], {x: 1}).get('part'), {x: 1});
});

test('camera state has schema-compatible finite bounds and null is an explicit reset', () => {
  assert.equal(normalizeView(null), null);
  assert.deepEqual(normalizeView({azimuth: Infinity, elevation: 8, distance: .1, orbit: -9}), {azimuth: .55, elevation: 1.56, distance: 3, orbit: -3.14});
});

test('toggles reject fractional and out-of-range values instead of introducing unsupported states', () => {
  const toggle = {...control('visible', 'opacity'), kind: 'toggle', min: 0, max: 1, value: 1, step: 1};
  const controls = [toggle], defaults = interactionDefaults(controls);
  for (const value of [.5, .001, -1, 2, true, '0', NaN, Infinity]) {
    assert.deepEqual(updateInteractionValues(controls, defaults, {visible: value}), {visible: 1});
    assert.equal(interactionOffsets(controls, {visible: value}).get('part').opacity, 0);
  }
  assert.deepEqual(updateInteractionValues(controls, defaults, {visible: 0}), {visible: 0});
  assert.deepEqual(updateInteractionValues(controls, {visible: 0}, {visible: 1}), {visible: 1});
  assert.equal(interactionOffsets(controls, {visible: 0}).get('part').opacity, -1);
});
