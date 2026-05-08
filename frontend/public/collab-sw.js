/* Service Worker for Contecflow Chat — Web Push */
/* eslint-disable no-restricted-globals */

self.addEventListener('install', (event) => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('push', (event) => {
  let data = {}
  try { data = event.data ? event.data.json() : {} } catch { data = { title: 'Contecflow Chat', body: event.data?.text() || '' } }
  const title = data.title || 'Contecflow Chat'
  const body = data.body || ''
  const tag = data.tag || 'collab'
  const url = data.url || '/chat'
  event.waitUntil(self.registration.showNotification(title, {
    body,
    tag,
    icon: '/favicon.ico',
    badge: '/favicon.ico',
    data: { url },
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const rawUrl = event.notification.data?.url || '/chat'
  // Whitelist: sólo rutas internas del mismo origen
  const ALLOWED_PATH_RE = /^\/(?:chat|portal|dashboard|tickets|projects|reports)(?:\/[\w\-]*)*$/
  const targetUrl = ALLOWED_PATH_RE.test(rawUrl) ? rawUrl : '/chat'
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const existing = all.find(c => c.url.includes('/chat'))
    if (existing) {
      existing.focus()
      try { existing.navigate(targetUrl) } catch { /* noop */ }
    } else {
      self.clients.openWindow(targetUrl)
    }
  })())
})
