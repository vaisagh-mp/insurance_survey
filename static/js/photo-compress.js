/**
 * SOTERIA Photo Compress compatibility layer.
 * Delegates to static/js/image-compress.js.
 */
(function (root) {
  if (root.ImageCompress) {
    root.SoteriaPhoto = root.ImageCompress;
  }
})(typeof self !== 'undefined' ? self : this);
