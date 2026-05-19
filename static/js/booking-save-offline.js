/**
 * Booking-level Save Offline controller.
 *
 * Replaces the per-document `.save-offline-btn` flow with a single button
 * at the top of the booking detail page. Clicking the button iterates the
 * list of documents emitted by the template (JSON in
 * `#booking-save-offline-data`) and caches each one through
 * `window.PWA.saveDocument`.
 *
 * Button states (driven by classes on the button):
 *   idle       — default, prompts user to save
 *   is-loading — request in flight
 *   is-saved   — every document on this booking is in IndexedDB
 *   is-error   — at least one document failed; clicking retries the lot
 *
 * Markup contract:
 *   <button id="booking-save-offline-btn" class="booking-save-offline-btn">
 *       <em class="icon ni ni-download"></em>
 *       <span class="booking-save-offline-btn__label">Save offline</span>
 *   </button>
 *   <script id="booking-save-offline-data" type="application/json">
 *     [{"url": "...", "description": "..."}, ...]
 *   </script>
 */
(function () {
    'use strict';

    var LABELS = {
        idle: 'Save offline',
        loading: 'Saving…',
        saved: 'Saved offline',
        error: 'Retry'
    };

    var ICONS = {
        idle: 'ni-download',
        loading: 'ni-loader',
        saved: 'ni-check-circle',
        error: 'ni-alert-circle'
    };

    function setState(button, state) {
        button.classList.remove('is-loading', 'is-saved', 'is-error');
        if (state === 'loading') button.classList.add('is-loading');
        else if (state === 'saved') button.classList.add('is-saved');
        else if (state === 'error') button.classList.add('is-error');

        var icon = button.querySelector('.icon');
        if (icon) {
            icon.classList.remove('ni-download', 'ni-loader', 'ni-check-circle', 'ni-alert-circle');
            icon.classList.add(ICONS[state] || ICONS.idle);
        }

        var label = button.querySelector('.booking-save-offline-btn__label');
        if (label) label.textContent = LABELS[state] || LABELS.idle;

        button.setAttribute('aria-label', LABELS[state] || LABELS.idle);
        button.disabled = state === 'loading';
    }

    function readDocuments() {
        var node = document.getElementById('booking-save-offline-data');
        if (!node) return [];
        try {
            var parsed = JSON.parse(node.textContent || '[]');
            if (!Array.isArray(parsed)) return [];
            return parsed.filter(function (d) { return d && d.url; });
        } catch (e) {
            console.warn('[booking-save-offline] Failed to parse documents payload:', e);
            return [];
        }
    }

    function saveAll(docs) {
        if (!window.PWA || typeof window.PWA.saveDocument !== 'function') {
            return Promise.reject(new Error('pwa_unavailable'));
        }
        return Promise.all(docs.map(function (doc) {
            return window.PWA.saveDocument({ url: doc.url, description: doc.description || '' })
                .then(function (reply) { return !!(reply && reply.ok); })
                .catch(function () { return false; });
        }));
    }

    function checkAllCached(docs) {
        if (!window.PWA || typeof window.PWA.isDocumentCached !== 'function') {
            return Promise.resolve(false);
        }
        return Promise.all(docs.map(function (doc) {
            return window.PWA.isDocumentCached(doc.url).catch(function () { return false; });
        })).then(function (results) {
            return results.length > 0 && results.every(Boolean);
        });
    }

    function handleClick(button, docs) {
        if (!docs.length) {
            setState(button, 'error');
            return;
        }
        setState(button, 'loading');
        saveAll(docs)
            .then(function (results) {
                var allOk = results.length > 0 && results.every(Boolean);
                setState(button, allOk ? 'saved' : 'error');
            })
            .catch(function () { setState(button, 'error'); });
    }

    function init() {
        var button = document.getElementById('booking-save-offline-btn');
        if (!button) return;

        var docs = readDocuments();
        setState(button, 'idle');

        button.addEventListener('click', function () { handleClick(button, docs); });

        // Reflect current cache state on load — if every doc on this booking
        // is already in IndexedDB, show the button as already saved.
        if (docs.length) {
            checkAllCached(docs).then(function (cached) {
                if (cached) setState(button, 'saved');
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
