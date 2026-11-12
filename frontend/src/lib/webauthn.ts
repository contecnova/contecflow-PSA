 

/** Credencial en JSON: el servidor manda el `id` en base64url. */
export interface CredentialDescriptorJSON extends Omit<PublicKeyCredentialDescriptor, 'id'> {
  id: string
}

/** `PublicKeyCredentialCreationOptions` tal como llegan del servidor (binarios en base64url). */
export interface CreationOptionsJSON extends Omit<PublicKeyCredentialCreationOptions, 'challenge' | 'user' | 'excludeCredentials'> {
  challenge: string
  user: Omit<PublicKeyCredentialUserEntity, 'id'> & { id: string }
  excludeCredentials?: CredentialDescriptorJSON[]
}

/** `PublicKeyCredentialRequestOptions` tal como llegan del servidor (binarios en base64url). */
export interface RequestOptionsJSON extends Omit<PublicKeyCredentialRequestOptions, 'challenge' | 'allowCredentials'> {
  challenge: string
  allowCredentials?: CredentialDescriptorJSON[]
}

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

export async function startRegistration(options: CreationOptionsJSON): Promise<Record<string, unknown>> {
  const { excludeCredentials, ...resto } = options
  const pk: PublicKeyCredentialCreationOptions = {
    ...resto,
    challenge: b64uToBuf(options.challenge),
    user: { ...options.user, id: b64uToBuf(options.user.id) },
  }
  if (Array.isArray(excludeCredentials)) {
    pk.excludeCredentials = excludeCredentials.map(c => ({ ...c, id: b64uToBuf(c.id) }))
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

export async function startAuthentication(options: RequestOptionsJSON): Promise<Record<string, unknown>> {
  const { allowCredentials, ...resto } = options
  const pk: PublicKeyCredentialRequestOptions = { ...resto, challenge: b64uToBuf(options.challenge) }
  if (Array.isArray(allowCredentials)) {
    pk.allowCredentials = allowCredentials.map(c => ({ ...c, id: b64uToBuf(c.id) }))
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
