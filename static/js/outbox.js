/**
 * SOTERIA Outbox compatibility layer.
 * Delegates to static/js/offline-sync.js.
 */
(function (root) {
  if (root.OfflineSync) {
    root.SoteriaOutbox = root.OfflineSync;
  }
})(typeof self !== 'undefined' ? self : this);
