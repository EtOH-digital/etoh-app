/* EtOH AI — Service Worker (minimal PWA shell cache)
 * Strategy:
 *   - Static assets (JS/CSS/images/fonts) : cache-first (stale-while-revalidate)
 *   - Navigation requests (HTML)          : network-first, fallback to cached shell
 *   - API requests (/api/*)               : network-only (never cache, freshness matters)
 */
const CACHE_NAME = 'etoh-shell-v1';
const SHELL_URLS = [
  '/',
  '/manifest.webmanifest',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Never intercept non-GET requests or cross-origin (e.g. Stripe, Sentry, LLM proxy).
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  // Never cache API calls — they must always be fresh.
  if (url.pathname.startsWith('/api/')) return;

  // Navigation: network-first, fallback to cached '/'
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put(request, copy)).catch(() => {});
          return resp;
        })
        .catch(() => caches.match(request).then((r) => r || caches.match('/')))
    );
    return;
  }

  // Static assets: cache-first with background revalidate
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((resp) => {
          if (resp && resp.ok) {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then((c) => c.put(request, copy)).catch(() => {});
          }
          return resp;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
