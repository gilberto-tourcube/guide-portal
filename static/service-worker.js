/**
 * Guide Portal — Service Worker
 *
 * Responsibilities:
 *   1. Cache static assets (CSS/JS/fonts) — cache-first.
 *   2. Cache visited HTML pages — network-first with offline fallback.
 *   3. Download document PDFs via backend proxy and store them in IndexedDB.
 *
 * Scope: '/' (root). Registration must set Service-Worker-Allowed: /.
 */

const CACHE_VERSION = 'guide-portal-v2';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const PAGE_CACHE = `${CACHE_VERSION}-pages`;
const IMAGE_CACHE = `${CACHE_VERSION}-images`;

const DB_NAME = 'guide-portal-documents';
const DB_VERSION = 1;
const STORE_NAME = 'documents';

// External hosts allowed through the SW cache (trip thumbnails, etc.)
const CACHEABLE_CROSS_ORIGIN_HOSTS = [
    'wasabisys.com',
    'amazonaws.com',
];

const OFFLINE_FALLBACK_HTML = `<!DOCTYPE html>
<html>
<head>
    <title>Offline</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:system-ui;padding:2rem;text-align:center;color:#364a63">
    <h2>You are offline</h2>
    <p>This page has not been cached yet. Please connect to the internet and try again.</p>
</body>
</html>`;

self.addEventListener('install', () => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) =>
            Promise.all(
                names
                    .filter((n) => !n.startsWith(CACHE_VERSION))
                    .map((n) => caches.delete(n))
            )
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    if (request.method !== 'GET') return;

    // Cross-origin: only cache images from trusted hosts (S3/Wasabi thumbnails)
    if (url.origin !== self.location.origin) {
        const hostname = url.hostname || '';
        const isTrustedHost = CACHEABLE_CROSS_ORIGIN_HOSTS.some((h) => hostname.endsWith(h));
        const isImage = request.destination === 'image' || /\.(jpe?g|png|gif|webp|svg)$/i.test(url.pathname);
        if (isTrustedHost && isImage) {
            event.respondWith(cacheFirst(request, IMAGE_CACHE, event));
        }
        return;
    }

    const skipPaths = ['/tourcube/', '/api/', '/manifest.json', '/service-worker.js', '/document-proxy'];
    if (skipPaths.some((path) => url.pathname.startsWith(path))) return;

    if (url.pathname.startsWith('/static/')) {
        event.respondWith(cacheFirst(request, STATIC_CACHE, event));
        return;
    }
    if (request.mode === 'navigate' || request.destination === 'document') {
        event.respondWith(networkFirst(request, PAGE_CACHE, event));
        return;
    }
});

self.addEventListener('message', (event) => {
    if (!event.data) return;

    if (event.data.type === 'CACHE_DOCUMENTS') {
        const docs = Array.isArray(event.data.docs) ? event.data.docs : [];
        event.waitUntil(cacheDocuments(docs));
        return;
    }

    if (event.data.type === 'CACHE_CURRENT_PAGE' && event.data.url && event.data.html) {
        event.waitUntil(cacheCurrentPage(event.data.url, event.data.html));
        return;
    }
});

async function cacheFirst(request, cacheName, event) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request, { ignoreVary: true });
    if (cached) return cached;
    try {
        const response = await fetch(request);
        // Accept successful same-origin (ok) or opaque cross-origin responses.
        const isOpaque = response && response.type === 'opaque';
        if (response && (response.ok || isOpaque)) {
            event.waitUntil(cache.put(request, response.clone()));
        }
        return response;
    } catch (err) {
        return cached || new Response('Offline', { status: 503 });
    }
}

async function networkFirst(request, cacheName, event) {
    const cache = await caches.open(cacheName);
    try {
        const response = await fetch(request);
        if (response && response.ok) {
            event.waitUntil(cache.put(request, response.clone()));
        }
        return response;
    } catch (err) {
        const cached = await cache.match(request, { ignoreVary: true });
        if (cached) return cached;
        return new Response(OFFLINE_FALLBACK_HTML, {
            status: 200,
            headers: { 'Content-Type': 'text/html; charset=utf-8' },
        });
    }
}

async function cacheCurrentPage(url, html) {
    const cache = await caches.open(PAGE_CACHE);
    const response = new Response(html, {
        status: 200,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
    await cache.put(new Request(url, { credentials: 'same-origin' }), response);
}

// ---------------- IndexedDB helpers ----------------

function openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'key' });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

function hasDocument(db, key) {
    return new Promise((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const req = tx.objectStore(STORE_NAME).getKey(key);
        req.onsuccess = () => resolve(!!req.result);
        req.onerror = () => resolve(false);
    });
}

function putDocument(db, entry) {
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).put(entry);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

function cacheKeyFromUrl(url) {
    const parsed = new URL(url);
    return parsed.origin + parsed.pathname;
}

async function cacheOneDocument(db, doc) {
    if (!doc || !doc.url) return;
    const key = cacheKeyFromUrl(doc.url);

    if (await hasDocument(db, key)) {
        console.log('[SW] Doc already cached:', key);
        return;
    }

    const proxyUrl = '/document-proxy?url=' + encodeURIComponent(doc.url);
    console.log('[SW] Fetching via proxy:', proxyUrl);
    const response = await fetch(proxyUrl, { credentials: 'same-origin' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const blob = await response.blob();
    await putDocument(db, {
        key,
        blob,
        description: doc.description || '',
        cachedAt: Date.now(),
    });
    console.log('[SW] Doc cached:', key, 'size:', blob.size);
}

async function cacheDocuments(docs) {
    console.log('[SW] cacheDocuments called with', docs.length, 'docs');
    if (!docs.length) return;
    try {
        const db = await openDB();
        await Promise.all(
            docs.map((doc) =>
                cacheOneDocument(db, doc).catch((err) => {
                    console.warn('[SW] Failed to cache document', doc.url, err);
                })
            )
        );
        console.log('[SW] cacheDocuments complete');
    } catch (err) {
        console.warn('[SW] cacheDocuments error', err);
    }
}
