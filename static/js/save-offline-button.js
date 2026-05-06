/**
 * Save Offline button controller.
 *
 * Wires every `.save-offline-btn` element on the page to the PWA API
 * exposed by pwa-offline.js (window.PWA.saveDocument / isDocumentCached).
 *
 * Button states (toggled via classes on the button):
 *   idle       — default, prompts user to save
 *   is-loading — request in flight
 *   is-saved   — document is in IndexedDB
 *   is-error   — last attempt failed; clicking retries
 *
 * Markup contract:
 *   <button class="save-offline-btn" data-doc-url="..." data-doc-description="...">
 *       <em class="icon ni ni-download"></em>
 *       <span class="save-offline-btn__label">Save offline</span>
 *   </button>
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

        var label = button.querySelector('.save-offline-btn__label');
        if (label) label.textContent = LABELS[state] || LABELS.idle;

        button.setAttribute('aria-label', LABELS[state] || LABELS.idle);
        // Keep button clickable in error state (retry); disable while loading.
        button.disabled = state === 'loading';
    }

    function handleClick(event) {
        var button = event.currentTarget;
        var url = button.getAttribute('data-doc-url');
        var description = button.getAttribute('data-doc-description') || '';
        if (!url) return;

        if (!window.PWA || typeof window.PWA.saveDocument !== 'function') {
            console.warn('[save-offline-btn] window.PWA.saveDocument unavailable');
            setState(button, 'error');
            return;
        }

        setState(button, 'loading');
        window.PWA.saveDocument({ url: url, description: description })
            .then(function (reply) {
                if (reply && reply.ok) setState(button, 'saved');
                else setState(button, 'error');
            })
            .catch(function () { setState(button, 'error'); });
    }

    function init() {
        var buttons = document.querySelectorAll('.save-offline-btn');
        if (!buttons.length) return;

        Array.prototype.forEach.call(buttons, function (button) {
            setState(button, 'idle');
            button.addEventListener('click', handleClick);
        });

        if (!window.PWA || typeof window.PWA.isDocumentCached !== 'function') return;

        // Reflect current cache state on load — runs in parallel for all docs.
        Array.prototype.forEach.call(buttons, function (button) {
            var url = button.getAttribute('data-doc-url');
            if (!url) return;
            window.PWA.isDocumentCached(url).then(function (cached) {
                if (cached) setState(button, 'saved');
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
