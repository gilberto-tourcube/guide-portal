/**
 * PWA offline support for Guide Portal.
 *
 * - Registers the service worker
 * - Sends document URLs to the SW for background caching (survives navigation)
 * - Replaces document link clicks with offline-aware handlers when offline
 *
 * Works on iOS Safari 11.3+ and Android Chrome.
 */
(function () {
    'use strict';

    var DB_NAME = 'guide-portal-documents';
    // v2 — must match service-worker.js DB_VERSION. Forces onupgradeneeded
    // to re-create the 'documents' store if it went missing (eviction or
    // interrupted upgrade left the DB at v1 with zero stores).
    var DB_VERSION = 2;
    var STORE_NAME = 'documents';

    // ---------------------------------------------------------------------
    // Service Worker registration
    //
    // On first visit the SW is installing while the page is already loaded,
    // so the current page bypasses the SW and never enters the page cache.
    // Once the SW activates we hand it the rendered HTML directly — this
    // avoids a second (slow) trip to the backend and still populates the
    // cache for offline reloads.
    // ---------------------------------------------------------------------
    function sendCurrentPageToCache(controller) {
        if (!controller) return;
        try {
            var html = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;
            controller.postMessage({
                type: 'CACHE_CURRENT_PAGE',
                url: window.location.href,
                html: html,
            });
        } catch (e) { /* ignore */ }
    }

    function registerServiceWorker() {
        if (window.__PWA_DISABLED__) return Promise.reject(new Error('PWA disabled by client gate'));
        if (!('serviceWorker' in navigator)) return Promise.reject(new Error('SW not supported'));

        var wasUncontrolled = !navigator.serviceWorker.controller;

        if (wasUncontrolled) {
            var warmed = false;
            navigator.serviceWorker.addEventListener('controllerchange', function () {
                if (warmed) return;
                warmed = true;
                sendCurrentPageToCache(navigator.serviceWorker.controller);
            });
        } else {
            // Already controlled — nothing to warm up.
        }

        return navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
    }

    /**
     * Wait for a controller — needed because the SW may not control the page
     * on first load. navigator.serviceWorker.ready resolves once active.
     */
    function waitForController() {
        if (!('serviceWorker' in navigator)) return Promise.reject();
        if (navigator.serviceWorker.controller) {
            return Promise.resolve(navigator.serviceWorker.controller);
        }
        return navigator.serviceWorker.ready.then(function (registration) {
            return registration.active || new Promise(function (resolve) {
                navigator.serviceWorker.addEventListener('controllerchange', function () {
                    resolve(navigator.serviceWorker.controller);
                }, { once: true });
            });
        });
    }

    // ---------------------------------------------------------------------
    // Bidirectional SW messaging via MessageChannel.
    // Each call gets its own port pair; resolves on first reply or rejects
    // on timeout / SW unavailable.
    // ---------------------------------------------------------------------
    function sendToSW(message, timeoutMs) {
        var to = typeof timeoutMs === 'number' ? timeoutMs : 30000;
        return waitForController().then(function (controller) {
            if (!controller) throw new Error('sw_unavailable');
            return new Promise(function (resolve, reject) {
                var channel = new MessageChannel();
                var settled = false;
                var timer = setTimeout(function () {
                    if (settled) return;
                    settled = true;
                    try { channel.port1.close(); } catch (e) { /* ignore */ }
                    reject(new Error('sw_timeout'));
                }, to);
                channel.port1.onmessage = function (event) {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timer);
                    try { channel.port1.close(); } catch (e) { /* ignore */ }
                    resolve(event.data);
                };
                try {
                    controller.postMessage(message, [channel.port2]);
                } catch (err) {
                    if (settled) return;
                    settled = true;
                    clearTimeout(timer);
                    reject(err);
                }
            });
        });
    }

    function saveDocument(doc) {
        if (!doc || !doc.url) return Promise.resolve({ ok: false, error: 'invalid_doc' });
        return sendToSW({ type: 'CACHE_DOCUMENT', doc: { url: doc.url, description: doc.description || '' } });
    }

    function isDocumentCached(url) {
        return sendToSW({ type: 'QUERY_CACHED_DOCUMENT', url: url }, 5000)
            .then(function (reply) { return !!(reply && reply.cached); })
            .catch(function () { return false; });
    }

    // ---------------------------------------------------------------------
    // IndexedDB read (for offline click handler)
    // ---------------------------------------------------------------------
    function openDB() {
        return new Promise(function (resolve, reject) {
            if (!('indexedDB' in window)) {
                reject(new Error('IndexedDB not supported'));
                return;
            }
            var req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function (e) {
                var db = e.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: 'key' });
                }
            };
            req.onsuccess = function (e) { resolve(e.target.result); };
            req.onerror = function (e) { reject(e.target.error); };
        });
    }

    function cacheKeyFromUrl(url) {
        try {
            var parsed = new URL(url);
            return parsed.origin + parsed.pathname;
        } catch (e) { return url; }
    }

    function getDocument(url) {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, 'readonly');
                var req = tx.objectStore(STORE_NAME).get(cacheKeyFromUrl(url));
                req.onsuccess = function () { resolve(req.result || null); };
                req.onerror = function () { reject(req.error); };
            });
        });
    }

    // ---------------------------------------------------------------------
    // Offline-aware click handler
    // ---------------------------------------------------------------------
    /**
     * Open a blob URL in a way that works across browser contexts.
     *
     * iOS Safari running as a standalone PWA silently no-ops `window.open`
     * (returns null, no popup). The only reliable way to view a PDF blob
     * inside a standalone PWA on iOS is to navigate the current document.
     * In a regular browser tab we still want to open in a new tab, so we
     * detect standalone mode and branch.
     *
     * `window.navigator.standalone` is the iOS-specific flag for an
     * installed home-screen PWA. `display-mode: standalone` covers the
     * cross-platform case (Android Chrome/Edge, desktop installs).
     */
    function isStandaloneMode() {
        return (
            (typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches) ||
            window.navigator.standalone === true
        );
    }

    /**
     * Open the cached document. Behavior splits on whether we're inside
     * a standalone PWA (#131):
     *
     * - Standalone (iOS home-screen PWA, Android installed PWA, desktop
     *   PWA): push a history entry, then navigate the current window to
     *   the blob URL. iOS hands off to its native PDF viewer with a
     *   Done button at the top; Done (or the swipe-back gesture) returns
     *   to this page, fires `popstate`, and the caller revokes the
     *   blob URL.
     * - Regular browser tab: open in a new tab so the user keeps the
     *   booking page in the original tab. Falls back to same-tab
     *   navigation if the popup is blocked.
     *
     * No in-app modal — the OS-native viewer is the right place to read
     * a PDF (full pagination, zoom, scroll). The history push is what
     * makes the back path obvious in standalone mode.
     */
    function openBlobUrl(blobUrl, onClose) {
        if (isStandaloneMode()) {
            try {
                history.pushState({ pwaDocOpen: true }, '', window.location.href);
            } catch (e) { /* some browsers reject pushState in obscure contexts — fall through */ }
            window.addEventListener('popstate', function handler() {
                window.removeEventListener('popstate', handler);
                if (typeof onClose === 'function') onClose();
            }, { once: true });
            window.location.href = blobUrl;
            return;
        }
        // Regular browser tab — open in a new tab.
        var win = window.open(blobUrl, '_blank');
        if (!win) {
            // Fallback if the browser blocked the popup. Same-tab navigation
            // is the safe option.
            window.location.href = blobUrl;
        }
    }

    function handleDocumentClick(event) {
        if (navigator.onLine) return; // online: browser handles it normally

        event.preventDefault();
        // Capture link state synchronously — `event.currentTarget` is
        // nulled out by the time the IDB promise resolves.
        var url = event.currentTarget.href;
        getDocument(url).then(function (entry) {
            if (!entry) {
                alert('This document has not been saved for offline viewing yet.');
                return;
            }
            var blobUrl = URL.createObjectURL(entry.blob);
            // Revoke as soon as the user comes back from the native viewer
            // (popstate) or after a long ceiling for the browser-tab path
            // where we can't observe the close.
            var revoked = false;
            function revoke() { if (!revoked) { revoked = true; URL.revokeObjectURL(blobUrl); } }
            openBlobUrl(blobUrl, revoke);
            setTimeout(revoke, 60000);
        }).catch(function (err) {
            console.warn('[PWA] Could not load cached document:', err);
            alert('Unable to open this document offline.');
        });
    }

    function attachClickHandlers() {
        var links = document.querySelectorAll('a[data-offline-cache="true"]');
        Array.prototype.forEach.call(links, function (link) {
            link.addEventListener('click', handleDocumentClick);
        });
    }

    /**
     * Strip `target="_blank"` from links flagged with `data-pwa-same-tab`
     * when running as a standalone PWA (#131). On iOS, `target="_blank"`
     * inside a standalone PWA ejects the user out into Safari, breaking
     * the back-to-app flow. In a regular browser tab we leave the link
     * alone so the existing new-tab behavior is preserved.
     */
    function adjustSameTabLinksForStandalone() {
        if (!isStandaloneMode()) return;
        var links = document.querySelectorAll('a[data-pwa-same-tab="true"]');
        Array.prototype.forEach.call(links, function (link) {
            link.removeAttribute('target');
            // `rel="noopener"` becomes irrelevant once target is gone, but leaving
            // it does no harm — same-origin same-tab navigation is unaffected.
        });
    }

    // ---------------------------------------------------------------------
    // Public API
    // ---------------------------------------------------------------------
    window.PWA = window.PWA || {};
    window.PWA.saveDocument = saveDocument;
    window.PWA.isDocumentCached = isDocumentCached;
    window.PWA.isStandalone = isStandaloneMode;

    // ---------------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------------
    function init() {
        attachClickHandlers();
        adjustSameTabLinksForStandalone();
        // Auto-cache removed — saving is now explicit, see booking-save-offline.js
    }

    window.addEventListener('load', function () {
        registerServiceWorker().catch(function (err) {
            if (err && /disabled by client gate/.test(err.message)) return;
            console.warn('[PWA] Service worker registration failed:', err);
        });
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
