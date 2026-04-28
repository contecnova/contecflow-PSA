const CACHE_NAME = 'contecflow-pwa-v24';
const API_CACHE  = 'contecflow-bi-api-v1';
const APP_SHELL  = ['/', '/index.html', '/manifest.json', '/contecflow-icon.svg', '/icon-192.png', '/icon-512.png'];

// BI API paths that benefit from stale-while-revalidate offline caching
const BI_CACHE_PATTERNS = [
  '/api/v1/analytics/olap/',
  '/api/v1/dashboard/projects-health',
  '/api/v1/bi/',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME && k !== API_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = request.url;

  // BI API endpoints: stale-while-revalidate for offline resilience
  const isBiApi = BI_CACHE_PATTERNS.some((p) => url.includes(p));
  if (isBiApi) {
    event.respondWith(
      caches.open(API_CACHE).then((cache) =>
        cache.match(request).then((cached) => {
          const networkFetch = fetch(request)
            .then((response) => {
              if (response && response.status === 200) {
                cache.put(request, response.clone());
              }
              return response;
            })
            .catch(() => cached || new Response(JSON.stringify({ error: 'Sin conexion' }), {
              headers: { 'Content-Type': 'application/json' },
              status: 503,
            }));
          // Return cached immediately; revalidate in background
          return cached || networkFetch;
        })
      )
    );
    return;
  }

  // Non-BI API: network-first; if offline return JSON fallback.
  if (url.includes('/api/')) {
    event.respondWith(
      fetch(request).catch(
        () =>
          new Response(JSON.stringify({ error: 'Sin conexion' }), {
            headers: { 'Content-Type': 'application/json' },
            status: 503,
          })
      )
    );
    return;
  }

  // App navigation: network-first, fallback to cached app shell.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put('/index.html', copy));
          return response;
        })
        .catch(() => caches.match('/index.html'))
    );
    return;
  }

  // Static assets: stale-while-revalidate for speed and freshness.
  event.respondWith(
    caches.match(request).then((cached) => {
      const networkFetch = fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);

      return cached || networkFetch;
    })
  );
});
