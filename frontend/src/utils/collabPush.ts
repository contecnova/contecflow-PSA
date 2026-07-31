/**
 * Register service worker + Web Push subscription against the backend.
 */

export type CollabPushFailureReason =
  | 'unsupported'
  | 'sw-register-failed'
  | 'permission-denied'
  | 'vapid-not-configured'

export type CollabPushResult =
  | { ok: true }
  | { ok: false; reason: CollabPushFailureReason; error?: string }

interface VapidPublicKeyResponse {
  configured?: boolean
  public_key?: string
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const b = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

export async function registerCollabPush(): Promise<CollabPushResult> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    return { ok: false, reason: 'unsupported' }
  }
  let reg: ServiceWorkerRegistration
  try {
    reg = await navigator.serviceWorker.register('/collab-sw.js', { scope: '/' })
  } catch (e) {
    return { ok: false, reason: 'sw-register-failed', error: String(e) }
  }
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') return { ok: false, reason: 'permission-denied' }

  // Envelope canónico: este bare-fetch no pasa por el interceptor de axios,
  // así que desenvolvemos {data,meta} → data manualmente.
  const pubRaw = await fetch('/api/v1/collaboration/push/public-key', { credentials: 'include' }).then(r => r.json())
  const pub: VapidPublicKeyResponse = (pubRaw && typeof pubRaw === 'object' && 'data' in pubRaw && 'meta' in pubRaw) ? pubRaw.data : pubRaw
  if (!pub?.configured || !pub?.public_key) return { ok: false, reason: 'vapid-not-configured' }

  let sub = await reg.pushManager.getSubscription()
  if (!sub) {
    // applicationServerKey expects BufferSource; Uint8Array satisfies it.
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(pub.public_key) as BufferSource,
    })
  }
  await fetch('/api/v1/collaboration/push/subscribe', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscription: sub.toJSON(), user_agent: navigator.userAgent }),
  })
  return { ok: true }
}
