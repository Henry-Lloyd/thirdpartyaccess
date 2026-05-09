/**
 * ThirdParty Access — Service Worker
 * Required for PWA installability. Provides offline caching of static assets
 * and a network-first strategy for API/dynamic content.
 */

const CACHE_NAME = 'tp-access-v1';

// Static assets to pre-cache on install
const PRECACHE_URLS = [
  '/',
  '/static/icons/favicon.png',
  '/static/logos/logo-icon.png',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

// ── Install: pre-cache critical assets ──
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
      .catch((err) => {
        console.warn('SW precache failed (non-critical):', err);
        return self.skipWaiting();
      })
  );
});

// ── Activate: clean up old caches ──
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// ── Fetch: network-first for dynamic content, cache-first for static assets ──
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests (POST forms, API mutations, etc.)
  if (event.request.method !== 'GET') return;

  // Skip cross-origin requests
  if (url.origin !== location.origin) return;

  // API requests: network-first (never serve stale API data)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Static assets: cache-first, then network
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response && response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages: network-first with offline fallback
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
