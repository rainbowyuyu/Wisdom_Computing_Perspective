/* Bounded declarative presentation state. No expressions or executable content. */
export const PROPERTY_LIMITS = Object.freeze({
  x: [-10000, 10000], y: [-10000, 10000], z: [-10000, 10000],
  rotation: [-10000, 10000], rotation_x: [-10000, 10000], rotation_y: [-10000, 10000],
  scale: [.01, 20], opacity: [0, 1], draw: [0, 1],
});
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

export function interactionDefaults(interactions = []) {
  return Object.fromEntries(interactions.map(control => [control.id, control.value]));
}

export function updateInteractionValues(interactions, previous, values) {
  const result = {...previous};
  for (const control of interactions) {
    const value = values?.[control.id];
    if (control.kind === 'toggle' && value !== 0 && value !== 1) continue;
    if (typeof value === 'number' && Number.isFinite(value)) result[control.id] = clamp(value, control.min, control.max);
  }
  return result;
}

export function dragValue(control, initial, pixels) {
  const value = initial + pixels * control.drag.sensitivity;
  if (value <= control.min) return control.min;
  if (value >= control.max) return control.max;
  return clamp(Number((control.min + Math.round((value - control.min) / control.step) * control.step).toPrecision(14)), control.min, control.max);
}

export function interactionOffsets(interactions = [], values = {}) {
  const result = new Map();
  for (const control of interactions) {
    const current = values[control.id];
    const valid = Number.isFinite(current) && (control.kind !== 'toggle' || current === 0 || current === 1);
    const delta = (valid ? clamp(current, control.min, control.max) : control.value) - control.value;
    for (const binding of control.bindings || []) {
      if (!Object.hasOwn(PROPERTY_LIMITS, binding.property) || !Number.isFinite(binding.multiplier)) continue;
      const offsets = result.get(binding.target_id) || {};
      offsets[binding.property] = (offsets[binding.property] || 0) + delta * binding.multiplier;
      result.set(binding.target_id, offsets);
    }
  }
  return result;
}

export function applyInteractionOffsets(state, offsets) {
  if (!offsets) return state;
  const result = {...state};
  for (const [property, delta] of Object.entries(offsets)) {
    if (!Object.hasOwn(PROPERTY_LIMITS, property)) continue;
    const limits = PROPERTY_LIMITS[property];
    if (limits) result[property] = clamp(result[property] + delta, ...limits);
  }
  return result;
}

export function normalizeView(camera) {
  if (camera == null) return null;
  const defaults = {azimuth: .55, elevation: .35, distance: 14, orbit: .3};
  const limits = {azimuth: [-10000, 10000], elevation: [-1.56, 1.56], distance: [3, 60], orbit: [-3.14, 3.14]};
  return Object.fromEntries(Object.keys(defaults).map(key => [key, clamp(typeof camera[key] === 'number' && Number.isFinite(camera[key]) ? camera[key] : defaults[key], ...limits[key])]));
}
