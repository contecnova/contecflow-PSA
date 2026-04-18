// Contecflow v22 Service Worker
const CACHE_NAME = 'contecflow-v22';

// Al instalar, limpiar todas las cachés anteriores
self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Network-first SIEMPRE — nunca servir caché de assets JS/CSS
self.addEventListener('fetch', (event) => {
  const { request } = event;
  // Solo interceptar GET
  if (request.method !== 'GET') return;
  // API: network-first, sin caché
  if (request.url.includes('/api/')) {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(JSON.stringify({ error: 'Sin conexión' }), {
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
    return;
  }
  // Archivos JS/CSS/JSX: SIEMPRE red (nunca caché) para evitar versiones obsoletas
  if (request.url.match(/\.(js|jsx|css|ts|tsx)(\?.*)?$/)) {
    event.respondWith(fetch(request));
    return;
  }
  // Resto: network-first
  event.respondWith(fetch(request).catch(() => caches.match(request)));
});
