/**
 * Guide Portal — PWA Offline client
 *
 * Registers the service worker, prefetches documents for offline use,
 * and intercepts document link clicks when offline (serving blobs from
 * IndexedDB).
 */
(function () {
    'use strict';

    var DB_NAME = 'guide-portal-documents';
    var DB_VERSION = 1;
    var STORE_NAME = 'documents';

    function cacheKeyFromUrl(url) {
        try {
            var parsed = new URL(url, window.location.origin);
            return parsed.origin + parsed.pathname;
        } catch (e) {
            return url;
        }
    }

    function openDB() {
        return new Promise(function (resolve, reject) {
            var req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function () {
                var db = req.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: 'key' });
                }
            };
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error); };
        });
    }

    function getDocument(url) {
        var key = cacheKeyFromUrl(url);
        return openDB().then(function (db) {
            return new Promise(function (resolve) {
                var tx = db.transaction(STORE_NAME, 'readonly');
                var req = tx.objectStore(STORE_NAME).get(key);
                req.onsuccess = function () { resolve(req.result || null); };
                req.onerror = function () { resolve(null); };
            });
        }).catch(function () { return null; });
    }

    function sendCurrentPageToCache(controller) {
        if (!controller) return;
        var html = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;
        controller.postMessage({
            type: 'CACHE_CURRENT_PAGE',
            url: window.location.href,
            html: html,
        });
    }

    function registerServiceWorker() {
        if (!('serviceWorker' in navigator)) return Promise.reject();

        var wasUncontrolled = !navigator.serviceWorker.controller;

        if (wasUncontrolled) {
            var warmed = false;
            navigator.serviceWorker.addEventListener('controllerchange', function () {
                if (warmed) return;
                warmed = true;
                sendCurrentPageToCache(navigator.serviceWorker.controller);
            });
        }

        return navigator.serviceWorker.register('/service-worker.js', { scope: '/' });
    }

    function waitForController() {
        if (navigator.serviceWorker.controller) {
            return Promise.resolve(navigator.serviceWorker.controller);
        }
        return navigator.serviceWorker.ready.then(function (registration) {
            if (navigator.serviceWorker.controller) {
                return navigator.serviceWorker.controller;
            }
            return new Promise(function (resolve) {
                navigator.serviceWorker.addEventListener('controllerchange', function () {
                    resolve(navigator.serviceWorker.controller);
                }, { once: true });
            });
        });
    }

    function requestDocumentCaching() {
        var links = document.querySelectorAll('a[data-offline-cache="true"]');
        console.log('[PWA] Found', links.length, 'docs to cache');
        if (!links.length) return;

        var docs = Array.prototype.map.call(links, function (link) {
            return {
                url: link.href,
                description: link.getAttribute('aria-label') || (link.textContent || '').trim(),
            };
        });

        waitForController().then(function (controller) {
            if (controller) {
                console.log('[PWA] Sending docs to SW');
                controller.postMessage({ type: 'CACHE_DOCUMENTS', docs: docs });
            } else {
                console.warn('[PWA] No SW controller — docs will not be cached this visit');
            }
        });
    }

    function handleDocumentClick(event) {
        if (navigator.onLine) return;  // online: browser opens normally

        event.preventDefault();
        var url = event.currentTarget.href;
        getDocument(url).then(function (entry) {
            if (!entry) {
                alert('This document has not been saved for offline viewing yet. Please visit the departure page while online to cache it.');
                return;
            }
            var blobUrl = URL.createObjectURL(entry.blob);
            // iOS Safari (especially in standalone PWA mode) blocks async
            // window.open. Navigating the current window is more reliable.
            window.location.href = blobUrl;
            setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 60000);
        }).catch(function (err) {
            console.warn('[PWA] Offline doc open failed', err);
            alert('Could not open offline document: ' + (err && err.message ? err.message : 'unknown error'));
        });
    }

    function attachDocumentClickHandlers() {
        var links = document.querySelectorAll('a[data-offline-cache="true"]');
        Array.prototype.forEach.call(links, function (link) {
            link.addEventListener('click', handleDocumentClick);
        });
    }

    function init() {
        if (!('serviceWorker' in navigator)) return;

        registerServiceWorker()
            .then(function () {
                requestDocumentCaching();
                attachDocumentClickHandlers();
            })
            .catch(function (err) {
                console.warn('[PWA] Service worker registration failed', err);
            });
    }

    if (document.readyState === 'loading') {
        window.addEventListener('load', init);
    } else {
        init();
    }
})();
