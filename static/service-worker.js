/**
 * Service Worker for Guide Portal PWA.
 *
 * Strategy:
 * - Static assets (/static/*): cache-first (fast repeat loads)
 * - Page navigations: network-first with cache fallback (works offline)
 * - API routes (/tourcube/, /api/, POST): never cached (always network)
 * - Document PDFs: downloaded and stored in IndexedDB on request from the
 *   client (via postMessage). The SW continues downloading even after the
 *   user navigates away, since it outlives the page.
 */

const CACHE_VERSION = 'guide-portal-v1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const PAGE_CACHE = `${CACHE_VERSION}-pages`;

const DB_NAME = 'guide-portal-documents';
// v2: ensure object store exists even if a previous failed open left the
// DB at v1 without the 'documents' store (observed after IDB eviction or
// interrupted upgrades). The onupgradeneeded handler is idempotent: it
// creates the store only if missing, so existing data is preserved.
const DB_VERSION = 2;
const STORE_NAME = 'documents';

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) =>
            Promise.all(
                names
                    .filter((name) => !name.startsWith(CACHE_VERSION))
                    .map((name) => caches.delete(name))
            )
        ).then(() => self.clients.claim())
    );
});

// ---------------------------------------------------------------------------
// Fetch: static + page caching
// ---------------------------------------------------------------------------
// Cross-origin image hosts allowed for offline caching. Trip thumbnails are
// served from these CDNs; if we don't cache them the booking-detail page
// renders broken images on cold offline launch.
const ALLOWED_IMG_HOSTS = ['amazonaws.com', 'wasabisys.com'];

self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    if (request.method !== 'GET') {
        return;
    }

    // Cross-origin: only cache images from allowed CDN hosts. Other
    // cross-origin requests are passed through untouched.
    if (url.origin !== self.location.origin) {
        const isAllowedHost = ALLOWED_IMG_HOSTS.some((h) => url.host.endsWith(h));
        if (request.destination === 'image' && isAllowedHost) {
            event.respondWith(cacheFirst(request, STATIC_CACHE, event));
        }
        return;
    }

    const skipPaths = ['/tourcube/', '/api/', '/manifest.json', '/service-worker.js'];
    if (skipPaths.some((path) => url.pathname.startsWith(path))) {
        return;
    }
    // Loading poll endpoints — always dynamic JSON, never cache.
    if (url.pathname.endsWith('/load')) {
        return;
    }

    if (url.pathname.startsWith('/static/')) {
        event.respondWith(cacheFirst(request, STATIC_CACHE, event));
        return;
    }

    if (request.mode === 'navigate' || request.destination === 'document') {
        event.respondWith(networkFirst(request, PAGE_CACHE, event));
        return;
    }
});

async function cacheFirst(request, cacheName, event) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request, { ignoreVary: true, ignoreSearch: false });
    if (cached) return cached;
    try {
        const response = await fetch(request);
        // Cache successful same-origin responses (response.ok) and any
        // opaque cross-origin responses (response.type === 'opaque',
        // status === 0). Opaque responses are cacheable but the browser
        // won't let us inspect their contents — that's fine for images.
        const cacheable = response.ok || response.type === 'opaque';
        if (cacheable) {
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
        if (response.ok) {
            // waitUntil keeps the SW alive until the cache write completes
            event.waitUntil(cache.put(request, response.clone()));
        }
        return response;
    } catch (err) {
        // Try exact match first.
        let cached = await cache.match(request, { ignoreVary: true });
        if (cached) return cached;

        const reqUrl = new URL(request.url);
        const keys = await cache.keys();

        // Candidate pathnames to serve, in priority order.
        //   1. Same pathname as the request (handles query-string drift).
        //   2. Root request → /guide/home, /vendor/home, /auth/login. The
        //      server-side redirect at "/" can't run offline, so fall back
        //      to whichever home page is actually cached.
        //   3. Parent path — e.g. /departure/{id} when /departure/{id}/foo
        //      isn't cached.
        const candidatePaths = [reqUrl.pathname];
        if (reqUrl.pathname === '/') {
            candidatePaths.push('/guide/home');
            candidatePaths.push('/vendor/home');
            candidatePaths.push('/auth/login');
        }
        const parts = reqUrl.pathname.split('/').filter(Boolean);
        if (parts.length > 1) {
            candidatePaths.push('/' + parts.slice(0, -1).join('/'));
        }

        for (const candidate of candidatePaths) {
            for (const cachedRequest of keys) {
                const cUrl = new URL(cachedRequest.url);
                if (cUrl.origin === reqUrl.origin && cUrl.pathname === candidate) {
                    const match = await cache.match(cachedRequest, { ignoreVary: true });
                    if (match) return match;
                }
            }
        }

        return new Response(
            '<!DOCTYPE html><html lang="en"><head>' +
            '<title>Offline</title>' +
            '<meta name="viewport" content="width=device-width,initial-scale=1">' +
            '<style>' +
            'body{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;margin:0;padding:2rem;color:#364a63;background:#f5f6fa;min-height:100vh;box-sizing:border-box;display:flex;align-items:center;justify-content:center}' +
            '.card{background:#fff;border-radius:12px;padding:2rem;max-width:400px;width:100%;text-align:center;box-shadow:0 2px 12px rgba(0,0,0,.06)}' +
            'h2{margin:0 0 .5rem;font-size:1.25rem}' +
            'p{margin:0 0 1.5rem;color:#8094ae;font-size:.95rem}' +
            '.actions{display:flex;flex-direction:column;gap:.5rem}' +
            'button,a.btn{display:inline-block;padding:.75rem 1.25rem;border-radius:8px;border:none;font-size:1rem;font-weight:500;cursor:pointer;text-decoration:none;text-align:center;box-sizing:border-box}' +
            '.primary{background:#526484;color:#fff}' +
            '.primary:active{background:#364a63}' +
            '.secondary{background:transparent;color:#526484;border:1px solid #dbdfea}' +
            '</style></head>' +
            '<body><div class="card">' +
            '<h2>You are offline</h2>' +
            '<p>This page has not been saved for offline viewing yet. Please connect to the internet and try again.</p>' +
            '<div class="actions">' +
            '<button class="primary" onclick="history.length>1?history.back():location.href=\'/guide/home\'">Go Back</button>' +
            '<a class="btn secondary" href="/guide/home">Go to Home</a>' +
            '</div>' +
            '</div></body></html>',
            { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
    }
}

// ---------------------------------------------------------------------------
// Document caching via postMessage from the client
// ---------------------------------------------------------------------------
self.addEventListener('message', (event) => {
    if (!event.data) return;

    if (event.data.type === 'CACHE_DOCUMENTS') {
        const docs = Array.isArray(event.data.docs) ? event.data.docs : [];
        event.waitUntil(cacheDocuments(docs));
        return;
    }

    // Explicit user-triggered single-document save with MessageChannel response.
    if (event.data.type === 'CACHE_DOCUMENT' && event.data.doc) {
        const port = event.ports && event.ports[0];
        event.waitUntil(cacheDocumentWithReply(event.data.doc, port));
        return;
    }

    // Read-only check: is this document already in IndexedDB?
    if (event.data.type === 'QUERY_CACHED_DOCUMENT' && event.data.url) {
        const port = event.ports && event.ports[0];
        event.waitUntil(queryCachedDocumentWithReply(event.data.url, port));
        return;
    }

    // First-visit warm-up: the page hands us its rendered HTML so we can
    // cache it without hitting the (often slow) backend again.
    if (event.data.type === 'CACHE_CURRENT_PAGE' && event.data.url && event.data.html) {
        event.waitUntil(cacheCurrentPage(event.data.url, event.data.html));
        return;
    }
});

async function cacheCurrentPage(url, html) {
    try {
        const cache = await caches.open(PAGE_CACHE);
        const response = new Response(html, {
            status: 200,
            headers: { 'Content-Type': 'text/html; charset=utf-8' },
        });
        await cache.put(new Request(url, { credentials: 'same-origin' }), response);
    } catch (err) {
        console.warn('[SW] Could not cache current page:', err);
    }
}

function cacheKeyFromUrl(url) {
    try {
        const parsed = new URL(url);
        return parsed.origin + parsed.pathname;
    } catch (e) {
        return url;
    }
}

function openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'key' });
            }
        };
        req.onsuccess = (e) => resolve(e.target.result);
        req.onerror = (e) => reject(e.target.error);
    });
}

function hasDocument(db, key) {
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const store = tx.objectStore(STORE_NAME);
        const req = store.getKey(key);
        req.onsuccess = () => resolve(!!req.result);
        req.onerror = () => reject(req.error);
    });
}

function putDocument(db, entry) {
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        const req = store.put(entry);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
    });
}

async function cacheDocuments(docs) {
    let db;
    try {
        db = await openDB();
    } catch (err) {
        console.warn('[SW] IndexedDB open failed:', err);
        return;
    }

    // Run downloads in parallel — SW keeps working while pending
    await Promise.all(docs.map((doc) => cacheOneDocument(db, doc)));
}

async function cacheOneDocument(db, doc) {
    if (!doc || !doc.url) return;
    const key = cacheKeyFromUrl(doc.url);

    try {
        if (await hasDocument(db, key)) return;

        // Fetch via same-origin proxy — S3/Wasabi presigned URLs don't allow
        // CORS from the browser, so direct fetch fails silently.
        const proxyUrl = '/document-proxy?url=' + encodeURIComponent(doc.url);
        const response = await fetch(proxyUrl, { credentials: 'same-origin' });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const blob = await response.blob();
        await putDocument(db, {
            key,
            blob,
            description: doc.description || '',
            cachedAt: Date.now(),
        });
    } catch (err) {
        console.warn('[SW] Could not cache document:', doc.description || doc.url, err.message);
    }
}

// Single-document save that surfaces success/error back to the caller.
// Throws on error so the explicit-save path can render an error state.
async function cacheDocumentWithReply(doc, port) {
    const reply = (msg) => { if (port) try { port.postMessage(msg); } catch (e) { /* port closed */ } };

    if (!doc || !doc.url) {
        reply({ ok: false, error: 'invalid_doc' });
        return;
    }

    let db;
    try {
        db = await openDB();
    } catch (err) {
        reply({ ok: false, error: 'indexeddb_open_failed' });
        return;
    }

    const key = cacheKeyFromUrl(doc.url);

    try {
        if (await hasDocument(db, key)) {
            reply({ ok: true, key, alreadyCached: true });
            return;
        }
        const proxyUrl = '/document-proxy?url=' + encodeURIComponent(doc.url);
        const response = await fetch(proxyUrl, { credentials: 'same-origin' });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const blob = await response.blob();
        await putDocument(db, {
            key,
            blob,
            description: doc.description || '',
            cachedAt: Date.now(),
        });
        reply({ ok: true, key });
    } catch (err) {
        reply({ ok: false, error: String(err && err.message || err) });
    }
}

async function queryCachedDocumentWithReply(url, port) {
    const reply = (msg) => { if (port) try { port.postMessage(msg); } catch (e) { /* port closed */ } };
    try {
        const db = await openDB();
        const cached = await hasDocument(db, cacheKeyFromUrl(url));
        reply({ cached: !!cached });
    } catch (err) {
        reply({ cached: false, error: String(err && err.message || err) });
    }
}
