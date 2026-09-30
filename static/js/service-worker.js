/**
 * SOTERIA Insurance Survey — Service Worker
 * Uses Workbox via CDN (runtime-only, no build step).
 *
 * Caching strategy:
 *   - App shell precaching (CSS, core JS, icons, offline fallback)
 *   - Navigation requests: NetworkFirst with cache fallback & /offline/ catch handler
 *   - Static assets: StaleWhileRevalidate
 *   - Images: CacheFirst
 *   - Catch-all fetch for POST navigation requests when offline (prevents ERR_INTERNET_DISCONNECTED)
 *   - Background Sync for 'sync-outbox' tag
 */

// Immediate activation
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

importScripts('https://storage.googleapis.com/workbox-cdn/releases/7.0.0/workbox-sw.js');

if (workbox) {
  console.log('[SW] Workbox loaded successfully');

  // Precache static asset shell, offline page, and sync-issues page
  workbox.precaching.precacheAndRoute([
    { url: '/offline/', revision: '4' },
    { url: '/sync-issues/', revision: '4' },
    { url: '/static/css/style.css', revision: '4' },
    { url: '/static/images/icon-192x192.png', revision: '4' },
    { url: '/static/images/icon-512x512.png', revision: '4' },
    { url: '/static/images/soteria_logo.png', revision: '4' },
    { url: '/static/js/offline-sync.js', revision: '4' },
    { url: '/static/js/sync-ui.js', revision: '4' },
    { url: '/static/js/image-compress.js', revision: '4' },
    { url: '/static/manifest.json', revision: '4' },
  ]);

  // App shell / HTML pages: NetworkFirst
  workbox.routing.registerRoute(
    ({ request }) => request.mode === 'navigate',
    new workbox.strategies.NetworkFirst({
      cacheName: 'soteria-pages',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 50,
          maxAgeSeconds: 24 * 60 * 60, // 1 day
        }),
      ],
    })
  );

  // Static assets: CSS, JS, Workers: StaleWhileRevalidate
  workbox.routing.registerRoute(
    ({ request }) =>
      request.destination === 'style' ||
      request.destination === 'script' ||
      request.destination === 'worker',
    new workbox.strategies.StaleWhileRevalidate({
      cacheName: 'soteria-static',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 60,
          maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
        }),
      ],
    })
  );

  // Images: CacheFirst
  workbox.routing.registerRoute(
    ({ request }) => request.destination === 'image',
    new workbox.strategies.CacheFirst({
      cacheName: 'soteria-images',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 100,
          maxAgeSeconds: 60 * 24 * 60 * 60, // 60 days
        }),
      ],
    })
  );

  // Google Fonts
  workbox.routing.registerRoute(
    ({ url }) => url.origin === 'https://fonts.googleapis.com',
    new workbox.strategies.StaleWhileRevalidate({
      cacheName: 'soteria-google-fonts-stylesheets',
    })
  );

  workbox.routing.registerRoute(
    ({ url }) => url.origin === 'https://fonts.gstatic.com',
    new workbox.strategies.CacheFirst({
      cacheName: 'soteria-google-fonts-webfonts',
      plugins: [
        new workbox.cacheableResponse.CacheableResponsePlugin({
          statuses: [0, 200],
        }),
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 30,
          maxAgeSeconds: 365 * 24 * 60 * 60, // 1 year
        }),
      ],
    })
  );

  // API calls: NetworkOnly (never cache API mutations or queries)
  workbox.routing.registerRoute(
    ({ url }) => url.pathname.startsWith('/api/'),
    new workbox.strategies.NetworkOnly()
  );

  // Offline catch handler for navigation requests
  workbox.routing.setCatchHandler(async ({ event }) => {
    if (event.request.mode === 'navigate') {
      const cached = await caches.match(event.request);
      if (cached) {
        return cached;
      }
      return caches.match('/offline/');
    }
    return Response.error();
  });
} else {
  console.error('[SW] Workbox failed to load');
}

// Fallback fetch listener for offline POST navigation requests (prevents browser dinosaur game)
self.addEventListener('fetch', (event) => {
  if (event.request.method === 'POST' && event.request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          return await fetch(event.request);
        } catch (err) {
          const offlinePage = await caches.match('/offline/');
          if (offlinePage) {
            return offlinePage;
          }
          return new Response(
            '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Offline</title></head><body style="font-family:sans-serif;text-align:center;padding:3rem;"><h2>Offline — Saved in Outbox</h2><p>Your request was submitted while offline. Please reconnect to sync.</p><a href="/">Return to Dashboard</a></body></html>',
            { status: 503, headers: { 'Content-Type': 'text/html' } }
          );
        }
      })()
    );
  }
});

// Background Sync Listener ('sync-outbox')
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-outbox' || event.tag === 'soteria-outbox-sync') {
    event.waitUntil(
      self.clients.matchAll({ type: 'window' }).then((clients) => {
        clients.forEach((client) => {
          client.postMessage({ type: 'SYNC_OUTBOX_TRIGGER' });
        });
      })
    );
  }
});
