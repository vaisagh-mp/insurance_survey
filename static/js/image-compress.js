/**
 * SOTERIA Client-Side Image Compression Helper
 *
 * Canvas-based resize to a maximum dimension (1920px by default)
 * with moderate JPEG quality (0.75 by default) before storing in
 * IndexedDB outbox or uploading.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ImageCompress = factory();
    // Compatibility alias
    root.SoteriaPhoto = root.ImageCompress;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DEFAULTS = {
    maxDimension: 1920,
    quality: 0.75,
    mimeType: 'image/jpeg',
  };

  /**
   * Calculate new dimensions preserving aspect ratio.
   */
  function calculateDimensions(width, height, maxDimension) {
    if (width <= maxDimension && height <= maxDimension) {
      return { width, height };
    }
    if (width > height) {
      return {
        width: maxDimension,
        height: Math.round((height * maxDimension) / width),
      };
    } else {
      return {
        width: Math.round((width * maxDimension) / height),
        height: maxDimension,
      };
    }
  }

  /**
   * Load an image source (Blob, File, or Image element) into an HTMLImageElement or ImageBitmap.
   */
  function loadImage(source) {
    if (typeof Image === 'undefined') {
      return Promise.reject(new Error('Image API not available in current environment'));
    }
    return new Promise((resolve, reject) => {
      if (source instanceof Image) {
        if (source.complete) return resolve(source);
        source.onload = () => resolve(source);
        source.onerror = (e) => reject(e);
        return;
      }
      const url = URL.createObjectURL(source);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = (e) => {
        URL.revokeObjectURL(url);
        reject(new Error('Failed to load image for compression'));
      };
      img.src = url;
    });
  }

  /**
   * Compress an image file/blob to a canvas-resized JPEG Blob.
   *
   * @param {File|Blob} file
   * @param {Object} [options]
   * @param {number} [options.maxDimension=1920] - Max width or height in pixels
   * @param {number} [options.quality=0.75] - JPEG quality (0.0 to 1.0)
   * @param {string} [options.mimeType='image/jpeg']
   * @returns {Promise<Blob>}
   */
  async function compressImage(file, options = {}) {
    const opts = { ...DEFAULTS, ...options };
    const maxDim = opts.maxDimension || opts.maxWidth || 1920;
    const quality = opts.quality !== undefined ? opts.quality : 0.75;
    const mimeType = opts.mimeType || 'image/jpeg';

    const img = await loadImage(file);
    const { width, height } = calculateDimensions(img.naturalWidth || img.width, img.naturalHeight || img.height, maxDim);

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    // High-quality downsampling
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, 0, 0, width, height);

    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => {
          if (blob) {
            resolve(blob);
          } else {
            reject(new Error('Canvas toBlob compression failed'));
          }
        },
        mimeType,
        quality
      );
    });
  }

  /**
   * Compress an image to a base64 Data URL string.
   */
  async function compressImageToBase64(file, options = {}) {
    const opts = { ...DEFAULTS, ...options };
    const maxDim = opts.maxDimension || opts.maxWidth || 1920;
    const quality = opts.quality !== undefined ? opts.quality : 0.75;
    const mimeType = opts.mimeType || 'image/jpeg';

    const img = await loadImage(file);
    const { width, height } = calculateDimensions(img.naturalWidth || img.width, img.naturalHeight || img.height, maxDim);

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, 0, 0, width, height);

    return canvas.toDataURL(mimeType, quality);
  }

  return {
    compressImage,
    compress: compressImage,
    compressImageToBase64,
    compressToBase64: compressImageToBase64,
    calculateDimensions,
    DEFAULTS,
  };
});
