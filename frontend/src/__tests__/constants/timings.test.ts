// Pilot test for centralized timing constants — audit #47.
// Guards against accidental sign-flip, zeroing, or breaking the documented
// ordering invariants (stale tiers, idle warn<logout, retry initial<max).
import { describe, it, expect } from 'vitest';
import * as T from '../../constants/timings';

describe('constants/timings', () => {
  it('TOAST_DEFAULT_MS is positive', () => {
    expect(typeof T.TOAST_DEFAULT_MS).toBe('number');
    expect(T.TOAST_DEFAULT_MS).toBeGreaterThan(0);
  });

  it('stale tiers grow monotonically: 5min < 15min < 1h', () => {
    expect(T.STALE_5_MIN_MS).toBeLessThan(T.STALE_15_MIN_MS);
    expect(T.STALE_15_MIN_MS).toBeLessThan(T.STALE_1_HOUR_MS);
  });

  it('IDLE_WARNING_MS fires strictly before IDLE_LOGOUT_MS', () => {
    expect(T.IDLE_WARNING_MS).toBeLessThan(T.IDLE_LOGOUT_MS);
  });

  it('retry backoff: initial delay < max delay', () => {
    expect(T.RETRY_INITIAL_DELAY_MS).toBeLessThan(T.RETRY_MAX_DELAY_MS);
  });

  it('all exported numeric constants are positive numbers', () => {
    // Catch-all: any accidental NaN / negative / zero slips here.
    for (const [name, value] of Object.entries(T)) {
      if (typeof value !== 'number') continue;
      if (name === 'STALE_ALWAYS') { expect(value).toBe(0); continue; }
      expect(Number.isFinite(value), `${name} must be finite`).toBe(true);
      expect(value, `${name} must be > 0`).toBeGreaterThan(0);
    }
  });
});
