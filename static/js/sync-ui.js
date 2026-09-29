/**
 * SOTERIA Sync Status UI — Banner, Online/Offline Badge, Outbox Indicator & Toasts
 *
 * Implements:
 *   1. Persistent Online/Offline badge with pending-item count, linked to /sync-issues/
 *   2. "You're viewing a saved copy — offline" banner when offline
 *   3. Real-time toast notifications for sync events
 */

(function () {
  'use strict';

  // ── DOM element creation ──────────────────────────────────────────────

  function createSyncBanner() {
    let banner = document.getElementById('soteria-sync-banner');
    if (banner) return banner;

    banner = document.createElement('div');
    banner.id = 'soteria-sync-banner';
    banner.className = 'sync-banner sync-banner--hidden';
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-live', 'polite');
    banner.innerHTML = `
      <div class="sync-banner__content">
        <span class="sync-banner__icon">⚡</span>
        <span class="sync-banner__text">You're viewing a saved copy — offline. Changes will be queued and synced when you reconnect.</span>
        <a href="/sync-issues/" class="sync-banner__link">View Outbox</a>
        <button type="button" class="sync-banner__close" aria-label="Dismiss">&times;</button>
      </div>
    `;
    document.body.prepend(banner);

    banner.querySelector('.sync-banner__close').addEventListener('click', () => {
      banner.classList.add('sync-banner--hidden');
    });

    return banner;
  }

  function createStatusBadge() {
    let container = document.getElementById('soteria-sync-status-badge');
    if (container) return container;

    container = document.createElement('li');
    container.id = 'soteria-sync-status-badge';
    container.className = 'sync-status-nav-item';
    container.innerHTML = `
      <a href="/sync-issues/" class="sync-status-link" title="Click to view Sync Issues and Outbox status">
        <span class="network-indicator network-indicator--online" id="soteria-network-dot"></span>
        <span class="network-label" id="soteria-network-text">Online</span>
        <span class="outbox-pill outbox-pill--hidden" id="soteria-outbox-badge" title="Pending offline items">
          <span class="outbox-icon">📤</span>
          <span class="outbox-count" id="soteria-outbox-count">0</span>
        </span>
      </a>
    `;

    const navLinks = document.querySelector('.nav-links');
    if (navLinks) {
      const firstVisible = navLinks.querySelector('li:not([style*="display: none"])');
      if (firstVisible) {
        navLinks.insertBefore(container, firstVisible);
      } else {
        navLinks.appendChild(container);
      }
    }

    return container;
  }

  function createToastContainer() {
    let container = document.getElementById('soteria-toast-container');
    if (container) return container;

    container = document.createElement('div');
    container.id = 'soteria-toast-container';
    container.className = 'toast-container';
    container.setAttribute('aria-live', 'polite');
    document.body.appendChild(container);
    return container;
  }

  function showToast(message, type = 'info', duration = 4000) {
    const container = createToastContainer();
    const toast = document.createElement('div');
    toast.className = `sync-toast sync-toast--${type}`;
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️';
    toast.innerHTML = `
      <span class="sync-toast__icon">${icon}</span>
      <span class="sync-toast__text">${message}</span>
    `;
    container.appendChild(toast);

    requestAnimationFrame(() => {
      toast.classList.add('sync-toast--visible');
    });

    setTimeout(() => {
      toast.classList.remove('sync-toast--visible');
      toast.addEventListener('transitionend', () => toast.remove());
    }, duration);
  }

  // ── State Updates ─────────────────────────────────────────────────────

  function updateNetworkStatus() {
    const banner = document.getElementById('soteria-sync-banner');
    const dot = document.getElementById('soteria-network-dot');
    const text = document.getElementById('soteria-network-text');

    if (navigator.onLine) {
      if (dot) {
        dot.className = 'network-indicator network-indicator--online';
      }
      if (text) text.textContent = 'Online';
      if (banner) banner.classList.add('sync-banner--hidden');
    } else {
      if (dot) {
        dot.className = 'network-indicator network-indicator--offline';
      }
      if (text) text.textContent = 'Offline';
      if (banner) banner.classList.remove('sync-banner--hidden');
    }
  }

  function updateOutboxBadge(count) {
    const badge = document.getElementById('soteria-outbox-badge');
    const countEl = document.getElementById('soteria-outbox-count');
    if (!badge || !countEl) return;

    if (count > 0) {
      countEl.textContent = count > 99 ? '99+' : String(count);
      badge.classList.remove('outbox-pill--hidden');
    } else {
      badge.classList.add('outbox-pill--hidden');
    }
  }

  // ── Initialization ───────────────────────────────────────────────────

  function init() {
    createSyncBanner();
    createStatusBadge();
    createToastContainer();
    updateNetworkStatus();

    window.addEventListener('online', () => {
      updateNetworkStatus();
      showToast('Back online — syncing pending offline changes…', 'success', 3000);
      if (window.OfflineSync) {
        window.OfflineSync.processOutbox();
      }
    });

    window.addEventListener('offline', () => {
      updateNetworkStatus();
      showToast("You're offline — changes will be saved to your local outbox.", 'warning', 4000);
    });

    window.addEventListener('soteria-outbox-count', (e) => {
      updateOutboxBadge(e.detail.count);
    });

    window.addEventListener('soteria-sync', (e) => {
      const { status, record } = e.detail;
      const label = (record && (record.label || record.entityType)) || 'Item';
      if (status === 'success') {
        showToast(`${label} synced successfully`, 'success');
      } else if (status === 'conflict') {
        showToast(`${label} conflict: modified on server. Check Sync Issues.`, 'warning', 5000);
      } else if (status === 'error') {
        showToast(`${label} sync failed: ${e.detail.details?.statusCode || 'Error'}`, 'error', 5000);
      }
    });

    if (window.OfflineSync) {
      window.OfflineSync.getPendingCount().then(updateOutboxBadge);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.SoteriaToast = showToast;
})();
