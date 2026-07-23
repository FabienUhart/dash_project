// [OFFLINE] Service worker network-first VERSIONNÉ — owner uniquement (index.html).
// Servi par la route Flask /sw.js qui remplace __BUILD__ par la version REALISATION (BUILD_VERSION)
// → un déploiement = un nouveau nom de cache, l'ancien purgé à l'activation. Aucune lib (invariant 6).
// Discipline stricte : network-first PARTOUT (en ligne = comportement identique, cache = filet),
// JAMAIS de cache des écritures, de /share/*, des non-200 ni des redirects (piège login Authelia).
'use strict';
const VERSION = '__BUILD__';
const SHELL_CACHE = 'dash-shell-' + VERSION;
const DATA_CACHE = 'dash-data-' + VERSION;
const MEDIA_CACHE = 'dash-media-' + VERSION;  // tuiles OSM + images dérivées, LRU FIFO
const MEDIA_MAX = 400;                          // entrées (borne LRU ~ dizaines de Mo)

// App-shell précaché (best-effort) — mêmes assets self-hébergés que la page.
const SHELL = [
  '/', '/static/favicon.svg', '/static/gsap.min.js',
  '/static/quill.min.js', '/static/quill.snow.css',
  '/static/quill-table-better.js', '/static/quill-table-better.css',
  '/static/leaflet.js', '/static/leaflet.css',
  '/static/leaflet.markercluster.js', '/static/MarkerCluster.css', '/static/MarkerCluster.Default.css',
  '/static/icon-192.png', '/static/icon-512.png',
];

self.addEventListener('install', (e) => {
  // NE PAS skipWaiting ici : la bascule est déclenchée par le clic sur l'invite [UPDATE-PROMPT].
  e.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    // purge de TOUT cache d'une version différente (dash-*-<autre version>).
    await Promise.all(keys.filter((k) => /^dash-(shell|data|media)-/.test(k) && !k.endsWith('-' + VERSION)).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

// [UPDATE-PROMPT] la page poste SKIP_WAITING au clic « Recharger » → bascule contrôlée.
self.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'SKIP_WAITING') self.skipWaiting();
});

function isMedia(url) {
  return /[?&]size=[ts](&|$)/.test(url.search) ||
    url.hostname.endsWith('tile.openstreetmap.org') ||
    (url.origin === self.location.origin && url.pathname.startsWith('/uploads/'));
}
function isCacheableData(url) {
  return url.origin === self.location.origin &&
    /^\/api\/(links|memos|projects|priorities|settings|version|categories|hubs|shares|guests|activity|favorites|fx|trash)$/.test(url.pathname);
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                 // jamais les écritures
  let url;
  try { url = new URL(req.url); } catch (_) { return; }
  if (url.pathname.startsWith('/share/')) return;   // invariant 5 : jamais le partage
  if (isMedia(url)) { e.respondWith(networkFirstMedia(req)); return; }
  if (url.origin === self.location.origin && (url.pathname === '/' || url.pathname.startsWith('/static/'))) {
    e.respondWith(networkFirst(req, SHELL_CACHE)); return;
  }
  if (isCacheableData(url)) { e.respondWith(networkFirst(req, DATA_CACHE)); return; }
  // tout le reste : réseau pur, jamais de cache (évite de figer une redirection Authelia).
});

async function networkFirst(req, cacheName) {
  try {
    const res = await fetch(req);
    // NE cacher QUE 200 same-origin NON redirigé (une redirection login ne doit jamais être figée).
    if (res && res.status === 200 && res.type === 'basic' && !res.redirected) {
      const c = await caches.open(cacheName);
      c.put(req, res.clone());
    }
    return res;
  } catch (err) {
    const cached = await caches.match(req);
    if (cached) return cached;
    throw err;
  }
}

async function networkFirstMedia(req) {
  try {
    const res = await fetch(req);
    // tuiles = réponses opaques (no-cors, status 0) : on les accepte ; dérivées = 200 same-origin.
    if (res && (res.status === 200 || res.type === 'opaque')) {
      const c = await caches.open(MEDIA_CACHE);
      await c.put(req, res.clone());
      trimCache(MEDIA_CACHE, MEDIA_MAX);
    }
    return res;
  } catch (err) {
    const cached = await caches.match(req);
    if (cached) return cached;
    throw err;
  }
}

async function trimCache(name, max) {
  const c = await caches.open(name);
  const keys = await c.keys();
  if (keys.length <= max) return;
  for (let i = 0; i < keys.length - max; i++) await c.delete(keys[i]);  // FIFO ≈ LRU
}
