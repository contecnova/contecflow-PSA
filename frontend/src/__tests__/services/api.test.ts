// Pilot test for unwrapList — the most-called helper in services/api.js.
// Audit #47: every list endpoint funnels through this normalizer, so a
// regression here breaks dozens of pages silently. We cover all backend
// response shapes documented in the JSDoc plus the legacy `{data: ...}`
// axios-style wrapper and the nested `{data: {items: [...]}}` case.
import { describe, it, expect } from 'vitest';
import { unwrapList } from '../../services/api';

describe('services/api · unwrapList', () => {
  it('returns a raw array as-is', () => {
    const arr = [1, 2, 3];
    expect(unwrapList(arr)).toBe(arr);
  });

  it('extracts items from {items: [...]}', () => {
    expect(unwrapList({ items: ['a', 'b'] })).toEqual(['a', 'b']);
  });

  it('returns [] for null', () => {
    expect(unwrapList(null)).toEqual([]);
  });

  it('returns [] for undefined', () => {
    expect(unwrapList(undefined)).toEqual([]);
  });

  it('unwraps axios-style {data: [...]} (legacy)', () => {
    const payload = [10, 20];
    expect(unwrapList({ data: payload })).toEqual(payload);
  });

  it('unwraps axios+paginated {data: {items: [...]}}', () => {
    expect(unwrapList({ data: { items: [{ id: 1 }] } })).toEqual([{ id: 1 }]);
  });

  it('honors a custom key when provided ({tickets: [...]})', () => {
    // Documented in JSDoc: unwrapList(resp, 'tickets') forces that key.
    expect(unwrapList({ tickets: ['t1'], items: ['ignored'] }, 'tickets'))
      .toEqual(['t1']);
  });

  it('falls back to [] when no array can be found', () => {
    expect(unwrapList({ unrelated: 'value' })).toEqual([]);
  });
});
