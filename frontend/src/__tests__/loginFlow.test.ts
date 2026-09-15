import { describe, expect, it } from 'vitest'
import { resolveLoginResponse } from '../utils/loginFlow'

describe('resolveLoginResponse', () => {
  it('detects MFA challenge responses', () => {
    const result = resolveLoginResponse({
      user: { id: '1' },
      mfa_required: true,
      mfa_challenge_token: 'challenge-123',
      mfa_methods: ['totp'],
    })

    expect(result.kind).toBe('mfa')
    // Estrecha la union: el `expect` de arriba comprueba en ejecucion pero
    // no cambia el tipo, y sin esto los accesos de abajo no compilan.
    if (result.kind !== 'mfa') throw new Error('se esperaba un reto MFA')
    expect(result.mfaChallengeToken).toBe('challenge-123')
    expect(result.mfaMethods).toEqual(['totp'])
  })

  it('detects successful logins', () => {
    const result = resolveLoginResponse({
      user: { id: '1', role: 'admin' },
    })

    expect(result.kind).toBe('success')
    if (result.kind !== 'success') throw new Error('se esperaba un login correcto')
    expect(result.user).toEqual({ id: '1', role: 'admin' })
  })

  it('reports missing MFA challenge as an error', () => {
    const result = resolveLoginResponse({
      user: { id: '1' },
      mfa_required: true,
      mfa_methods: ['totp'],
    })

    expect(result.kind).toBe('error')
    if (result.kind === 'error') {
      expect(result.message).toContain('MFA challenge')
    }
  })
})
