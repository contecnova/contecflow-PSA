/**
 * Register service worker + Web Push subscription against the backend.
 */
import { collabApi } from '../services/collaborationApi'

export type CollabPushFailureReason =
  | 'unsupported'
  | 'sw-register-failed'
  | 'permission-denied'
  | 'vapid-not-configured'

export type CollabPushResult =
  | { ok: true }
  | { ok: false; reason: CollabPushFailureReason; error?: string }

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

  // Por el cliente API: el interceptor ya desenvuelve {data,meta} → data.
  const pub = await collabApi.pushPublicKey()
  if (!pub?.configured || !pub?.public_key) return { ok: false, reason: 'vapid-not-configured' }

  let sub = await reg.pushManager.getSubscription()
  if (!sub) {
    // applicationServerKey expects BufferSource; Uint8Array satisfies it.
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(pub.public_key) as BufferSource,
    })
  }
  await collabApi.pushSubscribe({ subscription: sub.toJSON(), user_agent: navigator.userAgent })
  return { ok: true }
}
