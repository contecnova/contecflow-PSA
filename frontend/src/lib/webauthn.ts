/* eslint-disable @typescript-eslint/no-explicit-any */

function b64uToBuf(b64u: string): ArrayBuffer {
  const b64 = b64u.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (b64u.length % 4)) % 4)
  const bin = atob(b64)
  const buf = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
  return buf.buffer
}

function bufToB64u(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function webauthnSupported(): boolean {
  return typeof window !== 'undefined' && !!window.PublicKeyCredential && !!navigator.credentials
}

export async function startRegistration(options: Record<string, unknown>): Promise<Record<string, unknown>> {
  const pk = { ...options } as any
  pk.challenge = b64uToBuf(pk.challenge)
  pk.user = { ...pk.user, id: b64uToBuf(pk.user.id) }
  if (Array.isArray(pk.excludeCredentials)) {
    pk.excludeCredentials = pk.excludeCredentials.map((c: any) => ({ ...c, id: b64uToBuf(c.id) }))
  }
  const cred = (await navigator.credentials.create({ publicKey: pk })) as PublicKeyCredential
  const resp = cred.response as AuthenticatorAttestationResponse
  return {
    id: cred.id,
    rawId: bufToB64u(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufToB64u(resp.clientDataJSON),
      attestationObject: bufToB64u(resp.attestationObject),
    },
  }
}

export async function startAuthentication(options: Record<string, unknown>): Promise<Record<string, unknown>> {
  const pk = { ...options } as any
  pk.challenge = b64uToBuf(pk.challenge)
  if (Array.isArray(pk.allowCredentials)) {
    pk.allowCredentials = pk.allowCredentials.map((c: any) => ({ ...c, id: b64uToBuf(c.id) }))
  }
  const cred = (await navigator.credentials.get({ publicKey: pk })) as PublicKeyCredential
  const resp = cred.response as AuthenticatorAssertionResponse
  return {
    id: cred.id,
    rawId: bufToB64u(cred.rawId),
    type: cred.type,
    response: {
      clientDataJSON: bufToB64u(resp.clientDataJSON),
      authenticatorData: bufToB64u(resp.authenticatorData),
      signature: bufToB64u(resp.signature),
      userHandle: resp.userHandle ? bufToB64u(resp.userHandle) : null,
    },
  }
}
