export type LoginFlowResult =
  | { kind: 'success'; user: Record<string, unknown> }
  | { kind: 'mfa'; mfaChallengeToken: string; mfaMethods: string[]; user: Record<string, unknown> }
  | { kind: 'error'; message: string }

export function resolveLoginResponse(payload: Record<string, unknown>): LoginFlowResult {
  const user = (payload.user as Record<string, unknown> | undefined) ?? {}
  const mfaRequired = Boolean(payload.mfa_required)
  const mfaChallengeToken = typeof payload.mfa_challenge_token === 'string' ? payload.mfa_challenge_token : ''
  const rawMethods = payload.mfa_methods
  const mfaMethods = Array.isArray(rawMethods)
    ? rawMethods.filter((item): item is string => typeof item === 'string')
    : []

  const detail = typeof payload.detail === 'string' ? payload.detail : ''
  if (detail) {
    return { kind: 'error', message: detail }
  }

  if (mfaRequired && !mfaChallengeToken) {
    return { kind: 'error', message: 'MFA challenge was not returned by the server.' }
  }

  if (mfaRequired && mfaChallengeToken) {
    return {
      kind: 'mfa',
      mfaChallengeToken,
      mfaMethods,
      user,
    }
  }

  return { kind: 'success', user }
}
