/* Binai service worker — fresh updates for home-screen testers (iOS + Android).
 * Bump CACHE_VERSION on every frontend deploy so phones pick up the new app. */
const CACHE_VERSION = '20260724-30';
const CACHE_SHELL = 'binai-shell-' + CACHE_VERSION;

const NETWORK_FIRST = [
  '/',
  '/index.html',
  '/i18n-ui.js',
  '/sw.js',
  '/manifest.json',
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_SHELL).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (k) { return k.startsWith('binai-shell-') && k !== CACHE_SHELL; })
          .map(function (k) { return caches.delete(k); })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

function pathOnly(url) {
  try {
    var u = new URL(url);
    return u.pathname;
  } catch (e) {
    return url;
  }
}

function isNetworkFirst(url) {
  var p = pathOnly(url);
  if (p === '/' || p === '/index.html') return true;
  for (var i = 0; i < NETWORK_FIRST.length; i++) {
    if (p === NETWORK_FIRST[i] || p.endsWith(NETWORK_FIRST[i])) return true;
  }
  if (p.indexOf('/api/') !== -1) return true;
  return false;
}

self.addEventListener('fetch', function (event) {
  if (event.request.method !== 'GET') return;
  var url = event.request.url;
  if (url.indexOf('chrome-extension') !== -1) return;

  if (isNetworkFirst(url)) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  event.respondWith(
    caches.match(event.request).then(function (cached) {
      return cached || fetch(event.request);
    })
  );
});

function networkFirst(request) {
  return fetch(request).then(function (response) {
    return response;
  }).catch(function () {
    return caches.match(request).then(function (cached) {
      if (cached) return cached;
      return new Response('Offline — check your connection and try again.', {
        status: 503,
        headers: { 'Content-Type': 'text/plain' },
      });
    });
  });
}