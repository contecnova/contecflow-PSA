/**
 * Register service worker + Web Push subscription against the backend.
 */
function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const b = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

export async function registerCollabPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    return { ok: false, reason: 'unsupported' }
  }
  let reg
  try {
    reg = await navigator.serviceWorker.register('/collab-sw.js', { scope: '/' })
  } catch (e) {
    return { ok: false, reason: 'sw-register-failed', error: String(e) }
  }
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') return { ok: false, reason: 'permission-denied' }

  const pub = await fetch('/api/v1/collaboration/push/public-key', { credentials: 'include' }).then(r => r.json())
  if (!pub?.configured || !pub?.public_key) return { ok: false, reason: 'vapid-not-configured' }

  let sub = await reg.pushManager.getSubscription()
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(pub.public_key),
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
