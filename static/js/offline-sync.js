/**
 * SOTERIA Offline Sync & IndexedDB Outbox Manager
 *
 * Implements:
 *   - Universal offline form interceptor for all POST activity forms
 *   - IndexedDB outbox store for offline write requests
 *   - queueOrSend(request): immediate online attempt with offline fallback to outbox
 *   - processOutbox(): replaying queued items (JSON or FormData with files) in creation order
 *   - Background Sync ('sync-outbox') + universal fallback ('online', 'visibilitychange')
 *   - Client inspection for Sync Issues page (failed items, retry, discard)
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.OfflineSync = factory();
    // Alias for existing SoteriaOutbox compatibility
    root.SoteriaOutbox = root.OfflineSync;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DB_NAME = 'soteria-outbox';
  const DB_VERSION = 2;
  const STORE_NAME = 'outbox';
  const SYNC_TAG = 'sync-outbox';

  let _dbPromise = null;

  function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function getDB() {
    if (_dbPromise) return _dbPromise;
    _dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        let store;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        } else {
          store = event.target.transaction.objectStore(STORE_NAME);
        }
        if (!store.indexNames.contains('by_status')) {
          store.createIndex('by_status', 'status', { unique: false });
        }
        if (!store.indexNames.contains('by_createdAt')) {
          store.createIndex('by_createdAt', 'createdAt', { unique: false });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return _dbPromise;
  }

  function getStoredAuthHeaders() {
    const headers = {
      'Accept': 'application/json, text/html, */*',
    };
    if (typeof localStorage !== 'undefined') {
      const jwt =
        localStorage.getItem('jwt_access_token') ||
        localStorage.getItem('access_token') ||
        localStorage.getItem('token');
      if (jwt) {
        headers['Authorization'] = `Bearer ${jwt}`;
      }
    }
    // CSRF token from cookie or DOM for Django session auth
    if (typeof document !== 'undefined') {
      const match = document.cookie.match(/csrftoken=([^;]+)/);
      if (match) {
        headers['X-CSRFToken'] = match[1];
      }
    }
    return headers;
  }

  function dataURLtoFile(dataurl, filename) {
    const arr = dataurl.split(',');
    const mimeMatch = arr[0].match(/:(.*?);/);
    const mime = mimeMatch ? mimeMatch[1] : 'application/octet-stream';
    const bstr = atob(arr[1]);
    let n = bstr.length;
    const u8arr = new Uint8Array(n);
    while (n--) {
      u8arr[n] = bstr.charCodeAt(n);
    }
    return new File([u8arr], filename, { type: mime });
  }

  function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function getOutboxRecord(id) {
    const db = await getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const req = store.get(id);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function saveRecord(record) {
    const db = await getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const req = store.put(record);
      req.onsuccess = () => resolve(record);
      req.onerror = () => reject(req.error);
    });
  }

  async function deleteRecord(id) {
    const db = await getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const req = store.delete(id);
      req.onsuccess = () => {
        resolve();
        broadcastCount();
      };
      req.onerror = () => reject(req.error);
    });
  }

  async function getAllRecords() {
    const db = await getDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const req = store.getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  }

  async function getPendingCount() {
    const records = await getAllRecords();
    return records.filter((r) => r.status === 'pending' || r.status === 'syncing').length;
  }

  async function getPendingItems() {
    const records = await getAllRecords();
    return records
      .filter((r) => r.status === 'pending' || r.status === 'syncing')
      .sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  }

  async function getFailedItems() {
    const records = await getAllRecords();
    return records
      .filter((r) => r.status === 'failed')
      .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  }

  function broadcastCount() {
    if (typeof window !== 'undefined') {
      getPendingCount().then((count) => {
        window.dispatchEvent(
          new CustomEvent('soteria-outbox-count', { detail: { count } })
        );
      });
    }
  }

  function dispatchSyncEvent(status, record, details) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('soteria-sync', {
          detail: { status, record, details },
        })
      );
    }
  }

  /**
   * Register Background Sync ('sync-outbox') with fallback.
   */
  async function registerBackgroundSync() {
    if (
      typeof navigator !== 'undefined' &&
      'serviceWorker' in navigator &&
      'SyncManager' in window
    ) {
      try {
        const reg = await navigator.serviceWorker.ready;
        await reg.sync.register(SYNC_TAG);
        return true;
      } catch (err) {
        // Fall back to immediate manual sync if online
      }
    }
    return false;
  }

  function substituteTempId(target, tempId, realId) {
    if (!target || !tempId || realId === undefined || realId === null) return target;
    if (typeof target === 'string') {
      return target === String(tempId) ? realId : target.split(String(tempId)).join(String(realId));
    }
    if (Array.isArray(target)) {
      return target.map((item) => substituteTempId(item, tempId, realId));
    }
    if (typeof target === 'object') {
      const newObj = {};
      for (const [k, v] of Object.entries(target)) {
        if (v === tempId || String(v) === String(tempId)) {
          newObj[k] = realId;
        } else if (typeof v === 'object' && v !== null) {
          newObj[k] = substituteTempId(v, tempId, realId);
        } else if (typeof v === 'string' && v.includes(String(tempId))) {
          newObj[k] = v.split(String(tempId)).join(String(realId));
        } else {
          newObj[k] = v;
        }
      }
      return newObj;
    }
    return target;
  }

  function getPrereqIds(dependsOn) {
    if (!dependsOn) return [];
    if (Array.isArray(dependsOn)) return dependsOn.map(String);
    if (typeof dependsOn === 'object') return Object.values(dependsOn).map(String);
    return [String(dependsOn)];
  }

  /**
   * queueOrSend(request):
   * Tries fetch immediately if online and no pending prerequisites exist.
   * On network failure or if offline, writes the request to the outbox.
   */
  async function queueOrSend(request) {
    const id = request.id || generateUUID();
    const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true;

    const record = {
      id,
      method: (request.method || 'POST').toUpperCase(),
      url: request.url,
      payload: request.payload !== undefined ? request.payload : (request.body || null),
      formFields: request.formFields || null,
      files: request.files || null,
      label: request.label || '',
      createdAt: request.createdAt || new Date().toISOString(),
      entityType: request.entityType || 'unknown',
      entityId: request.entityId || null,
      tempId: request.tempId || null,
      dependsOn: request.dependsOn || null,
      baseVersion: request.baseVersion || request.base_updated_at || null,
      status: 'pending',
      failureReason: null,
      lastError: null,
      headers: request.headers || {},
      retryCount: 0,
    };

    let hasPendingPrereqs = false;
    if (record.dependsOn) {
      const prereqs = getPrereqIds(record.dependsOn);
      const pendingItems = await getPendingItems();
      if (pendingItems.some((p) => prereqs.includes(String(p.id)) || (p.tempId && prereqs.includes(String(p.tempId))))) {
        hasPendingPrereqs = true;
      }
    }

    if (isOnline && !hasPendingPrereqs) {
      try {
        let fetchBody;
        let fetchHeaders = { ...getStoredAuthHeaders(), ...record.headers };

        if (record.formFields || (record.files && record.files.length > 0)) {
          const formData = new FormData();
          if (record.formFields) {
            for (const [k, v] of Object.entries(record.formFields)) {
              if (Array.isArray(v)) {
                v.forEach((val) => formData.append(k, val));
              } else if (v !== null && v !== undefined) {
                formData.append(k, v);
              }
            }
          }
          if (record.files && Array.isArray(record.files)) {
            for (const f of record.files) {
              if (f.dataUrl && f.name) {
                const fileObj = dataURLtoFile(f.dataUrl, f.name);
                formData.append(f.fieldName || 'file', fileObj, f.name);
              }
            }
          }
          delete fetchHeaders['Content-Type'];
          fetchBody = formData;
        } else {
          let bodyData = record.payload;
          if (record.baseVersion && typeof bodyData === 'object' && bodyData !== null) {
            bodyData = { ...bodyData, base_updated_at: record.baseVersion };
            fetchHeaders['If-Match'] = record.baseVersion;
          }
          fetchHeaders['Content-Type'] = 'application/json';
          fetchBody = bodyData ? (typeof bodyData === 'string' ? bodyData : JSON.stringify(bodyData)) : undefined;
        }

        const fetchOptions = {
          method: record.method,
          headers: fetchHeaders,
          body: fetchBody,
          credentials: 'same-origin',
        };

        const response = await fetch(record.url, fetchOptions);

        if (response.ok) {
          dispatchSyncEvent('success', record, { statusCode: response.status });
          return { immediate: true, status: 'synced', response };
        }

        if (response.status === 409) {
          record.status = 'failed';
          record.failureReason = 'conflict';
          const errData = await response.json().catch(() => ({}));
          record.lastError = errData.detail || 'Conflict: Modified on server';
          await saveRecord(record);
          broadcastCount();
          dispatchSyncEvent('conflict', record, errData);
          return { immediate: true, queued: true, status: 'failed', record };
        }

        if (response.status === 401) {
          record.status = 'failed';
          record.failureReason = 'expired_auth';
          record.lastError = 'Session expired / Invalid authentication';
          await saveRecord(record);
          broadcastCount();
          dispatchSyncEvent('error', record, { statusCode: 401 });
          return { immediate: true, queued: true, status: 'failed', record };
        }

        return { immediate: true, status: 'error', response };
      } catch (err) {
        // Network failure -> write to outbox
      }
    }

    // Write into outbox
    record.status = 'pending';
    await saveRecord(record);
    broadcastCount();

    // Trigger background sync registration
    await registerBackgroundSync();

    return { queued: true, status: 'pending', record };
  }

  /**
   * processOutbox():
   * Replays pending items via fetch respecting dependency order and substituting real IDs.
   */
  let _isProcessing = false;

  async function processOutbox() {
    if (_isProcessing) return;
    _isProcessing = true;

    try {
      const allRecords = await getAllRecords();
      const idMap = new Map();
      const failedPrereqIds = new Set();

      allRecords.forEach((r) => {
        if (r.status === 'failed') {
          if (r.id) failedPrereqIds.add(String(r.id));
          if (r.tempId) failedPrereqIds.add(String(r.tempId));
        }
      });

      let madeProgress = true;
      while (madeProgress) {
        madeProgress = false;
        const currentRecords = await getAllRecords();
        const pendingRecords = currentRecords
          .filter((r) => r.status === 'pending')
          .sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));

        if (pendingRecords.length === 0) break;

        for (const record of pendingRecords) {
          const prereqIds = getPrereqIds(record.dependsOn);

          // 1. If any prerequisite failed (e.g. 409), leave dependents pending
          const hasFailedPrereq = prereqIds.some((pId) => failedPrereqIds.has(pId));
          if (hasFailedPrereq) {
            continue;
          }

          // 2. If any prerequisite is still pending in outbox (and not in idMap), wait for it to process first
          const hasUnresolvedPrereqInPending = prereqIds.some((pId) => {
            if (idMap.has(pId)) return false;
            return pendingRecords.some((pr) => pr.id !== record.id && (String(pr.id) === pId || String(pr.tempId) === pId));
          });
          if (hasUnresolvedPrereqInPending) {
            continue;
          }

          // 3. Substitute all resolved prerequisite IDs
          if (prereqIds.length > 0) {
            let modified = false;
            for (const pId of prereqIds) {
              if (idMap.has(pId)) {
                const realId = idMap.get(pId);
                record.payload = substituteTempId(record.payload, pId, realId);
                record.formFields = substituteTempId(record.formFields, pId, realId);
                record.url = substituteTempId(record.url, pId, realId);
                modified = true;
              }
            }
            if (modified) {
              const remaining = prereqIds.filter((pId) => !idMap.has(pId));
              record.dependsOn = remaining.length > 0 ? remaining : null;
              await saveRecord(record);
            }
          }

          // 4. Never send a dependent record still holding a temp id
          if (record.dependsOn && getPrereqIds(record.dependsOn).length > 0) {
            continue;
          }

          record.status = 'syncing';
          await saveRecord(record);
          madeProgress = true;

          try {
            let fetchBody;
            let fetchHeaders = { ...getStoredAuthHeaders(), ...record.headers };

            if (record.formFields || (record.files && record.files.length > 0)) {
              const formData = new FormData();
              if (record.formFields) {
                for (const [k, v] of Object.entries(record.formFields)) {
                  if (Array.isArray(v)) {
                    v.forEach((val) => formData.append(k, val));
                  } else if (v !== null && v !== undefined) {
                    formData.append(k, v);
                  }
                }
              }
              if (record.files && Array.isArray(record.files)) {
                for (const f of record.files) {
                  if (f.dataUrl && f.name) {
                    const fileObj = dataURLtoFile(f.dataUrl, f.name);
                    formData.append(f.fieldName || 'file', fileObj, f.name);
                  }
                }
              }
              delete fetchHeaders['Content-Type'];
              fetchBody = formData;
            } else {
              let bodyData = record.payload;
              if (record.baseVersion && typeof bodyData === 'object' && bodyData !== null) {
                bodyData = { ...bodyData, base_updated_at: record.baseVersion };
                fetchHeaders['If-Match'] = record.baseVersion;
              }
              fetchHeaders['Content-Type'] = 'application/json';
              fetchBody = bodyData ? (typeof bodyData === 'string' ? bodyData : JSON.stringify(bodyData)) : undefined;
            }

            const response = await fetch(record.url, {
              method: record.method,
              headers: fetchHeaders,
              body: fetchBody,
              credentials: 'same-origin',
            });

            if (response.ok) {
              const resData = await response.clone().json().catch(() => null);
              const realId = resData && (resData.id || resData.pk);
              if (realId) {
                idMap.set(String(record.id), realId);
                if (record.tempId) idMap.set(String(record.tempId), realId);
                if (record.entityId) idMap.set(String(record.entityId), realId);
              }
              await deleteRecord(record.id);
              dispatchSyncEvent('success', record, { statusCode: response.status });
            } else if (response.status === 409) {
              record.status = 'failed';
              record.failureReason = 'conflict';
              const errData = await response.json().catch(() => ({}));
              record.lastError = errData.detail || 'Conflict: Modified on server';
              failedPrereqIds.add(String(record.id));
              if (record.tempId) failedPrereqIds.add(String(record.tempId));
              await saveRecord(record);
              dispatchSyncEvent('conflict', record, errData);
            } else if (response.status === 401) {
              record.status = 'failed';
              record.failureReason = 'expired_auth';
              record.lastError = 'Session expired / Invalid authentication';
              failedPrereqIds.add(String(record.id));
              if (record.tempId) failedPrereqIds.add(String(record.tempId));
              await saveRecord(record);
              dispatchSyncEvent('error', record, { statusCode: 401 });
            } else {
              record.status = 'failed';
              record.failureReason = 'other';
              const errText = await response.text().catch(() => '');
              record.lastError = `Server returned ${response.status}: ${errText.slice(0, 100)}`;
              failedPrereqIds.add(String(record.id));
              if (record.tempId) failedPrereqIds.add(String(record.tempId));
              await saveRecord(record);
              dispatchSyncEvent('error', record, { statusCode: response.status });
            }
          } catch (networkError) {
            record.status = 'pending';
            record.retryCount = (record.retryCount || 0) + 1;
            await saveRecord(record);
            return;
          }
        }
      }
    } finally {
      _isProcessing = false;
      broadcastCount();
    }
  }

  async function retryFailedItem(id) {
    const record = await getOutboxRecord(id);
    if (record) {
      record.status = 'pending';
      record.failureReason = null;
      record.lastError = null;
      await saveRecord(record);
      broadcastCount();
      return processOutbox();
    }
  }

  async function retryAllFailed() {
    const failed = await getFailedItems();
    for (const record of failed) {
      record.status = 'pending';
      record.failureReason = null;
      record.lastError = null;
      await saveRecord(record);
    }
    broadcastCount();
    return processOutbox();
  }

  async function discardItem(id) {
    await deleteRecord(id);
  }

  async function discardAllFailed() {
    const failed = await getFailedItems();
    for (const record of failed) {
      await deleteRecord(record.id);
    }
  }

  /**
   * Handle form submit asynchronously after synchronous event prevention.
   */
  async function handleOfflineFormSubmit(form, action) {
    const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
    const originalText = submitBtn ? (submitBtn.innerHTML || submitBtn.value || '').trim() : '';

    // Determine human-readable label BEFORE changing submitBtn's text
    let label = form.getAttribute('data-label');
    if (!label) {
      const heading =
        form.closest('.form-card')?.querySelector('h1, h2, h3, h4, .card-table-title') ||
        form.querySelector('h1, h2, h3, h4, .card-table-title');
      if (heading) {
        label = heading.textContent.trim().replace(/^\+\s*/, '');
      }
    }
    if (!label) {
      label = originalText && originalText !== 'Saving to Outbox…' ? originalText : 'Form Action';
    }

    if (submitBtn) {
      submitBtn.disabled = true;
      if (submitBtn.tagName === 'BUTTON') submitBtn.textContent = 'Saving to Outbox…';
    }

    try {
      const formData = new FormData(form);
      const formFields = {};
      const files = [];

      for (const [key, value] of formData.entries()) {
        if (value instanceof File) {
          if (value.size > 0 && value.name) {
            let dataUrl;
            try {
              if (value.type.startsWith('image/') && typeof window.ImageCompress !== 'undefined') {
                dataUrl = await window.ImageCompress.compressImageToBase64(value);
              } else {
                dataUrl = await readFileAsDataURL(value);
              }
            } catch (imgErr) {
              console.warn('[OfflineSync] Image compression failed, using raw dataURL:', imgErr);
              dataUrl = await readFileAsDataURL(value);
            }
            files.push({
              fieldName: key,
              name: value.name,
              type: value.type,
              dataUrl: dataUrl,
            });
          }
        } else {
          if (formFields[key] !== undefined) {
            if (!Array.isArray(formFields[key])) {
              formFields[key] = [formFields[key]];
            }
            formFields[key].push(value);
          } else {
            formFields[key] = value;
          }
        }
      }

      let entityType = 'Activity';
      let entityId = null;
      let tempId = null;
      let dependsOn = null;

      if (action.includes('insurers/add') || action.includes('insurer/add')) {
        entityType = 'insurer';
        tempId = 'temp_insurer_' + Date.now();
      } else if (action.includes('insured/add')) {
        entityType = 'insured';
        tempId = 'temp_insured_' + Date.now();
      } else if (action.includes('policies/add') || action.includes('policy/add')) {
        entityType = 'policy';
        tempId = 'temp_policy_' + Date.now();
      } else if (action.includes('claims/create') || action.endsWith('/claims/')) {
        entityType = 'Claim';
        const prereqs = [];
        ['insurer', 'insured', 'policy'].forEach((field) => {
          const val = formFields[field];
          if (val && (String(val).startsWith('temp') || isNaN(Number(val)))) {
            prereqs.push(String(val));
          }
        });
        if (prereqs.length > 0) dependsOn = prereqs;
      }

      const claimMatch = action.match(/claims\/(\d+)/);
      if (claimMatch) {
        entityId = claimMatch[1];
        if (action.includes('inspection')) entityType = 'Inspection';
        else if (action.includes('lor')) entityType = 'LOR / Requirement';
        else if (action.includes('assessment')) entityType = 'Assessment';
        else if (action.includes('documents')) entityType = 'Document';
        else if (action.includes('invoices')) entityType = 'Repair Invoice';
        else if (action.includes('billing')) entityType = 'Billing';
        else if (action.includes('report')) entityType = 'Report';
        else if (action.includes('assign')) entityType = 'Assignment';
        else if (action.includes('approve-and-close')) entityType = 'Claim Closure';
      }

      if (tempId) {
        const entityLabel = (formFields.name || formFields.policy_number || 'New ' + entityType) + ' (Offline)';
        if (typeof BroadcastChannel !== 'undefined') {
          try {
            const bc = new BroadcastChannel('soteria_master_data');
            bc.postMessage({
              type: 'ENTITY_CREATED',
              entityType: entityType,
              id: tempId,
              label: entityLabel,
              extra: { insurer_id: formFields.insurer || null },
            });
          } catch (e) {}
        }
        if (window.opener && !window.opener.closed) {
          try {
            window.opener.postMessage(
              {
                type: 'ENTITY_CREATED',
                entityType: entityType,
                id: tempId,
                label: entityLabel,
                extra: { insurer_id: formFields.insurer || null },
              },
              '*'
            );
          } catch (e) {}
        }
      }

      await queueOrSend({
        url: action,
        method: 'POST',
        formFields: formFields,
        files: files,
        label: label,
        entityType: entityType,
        entityId: entityId,
        tempId: tempId,
        dependsOn: dependsOn,
        headers: {},
      });

      if (typeof window.SoteriaToast === 'function') {
        window.SoteriaToast(`Saved offline! "${label}" queued in Outbox.`, 'success', 5000);
      }

      let feedback = form.querySelector('.soteria-form-offline-notice');
      if (!feedback) {
        feedback = document.createElement('div');
        feedback.className = 'soteria-form-offline-notice';
        feedback.style.cssText =
          'margin-top: 1rem; padding: 0.75rem 1rem; border-radius: 6px; background-color: #fef3c7; color: #92400e; font-size: 0.85rem; border: 1px solid #fcd34d; font-weight: 500;';
        form.appendChild(feedback);
      }
      feedback.innerHTML = `⚡ <strong>Saved Offline:</strong> "${label}" has been safely queued in your <a href="/sync-issues/" style="color: #b45309; text-decoration: underline; font-weight: 700;">Offline Outbox</a>. It will automatically sync when you reconnect.`;
      if (typeof feedback.scrollIntoView === 'function') {
        feedback.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }

      if (
        form.id === 'claimDocumentUploadForm' ||
        action.includes('/upload')
      ) {
        form.reset();
      }

      if (submitBtn) {
        submitBtn.disabled = false;
        if (submitBtn.tagName === 'BUTTON') submitBtn.innerHTML = originalText;
      }
    } catch (err) {
      console.error('[OfflineSync] Offline form submission error:', err);
      alert('Could not save to offline outbox: ' + err.message);
      if (submitBtn) {
        submitBtn.disabled = false;
        if (submitBtn.tagName === 'BUTTON') submitBtn.innerHTML = originalText;
      }
    }
  }

  /**
   * Universal Offline Form Interceptor
   */
  function attachUniversalOfflineFormInterceptor() {
    if (typeof document === 'undefined') return;

    if (typeof window !== 'undefined') {
      window._soteriaIsOffline = !navigator.onLine;
      window.addEventListener('online', () => { window._soteriaIsOffline = false; });
      window.addEventListener('offline', () => { window._soteriaIsOffline = true; });
    }

    function isDeviceOffline() {
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return true;
      if (typeof window !== 'undefined' && window._soteriaIsOffline === true) return true;
      const dot = document.getElementById('soteria-network-dot');
      if (dot && dot.classList.contains('network-indicator--offline')) return true;
      return false;
    }

    document.addEventListener(
      'submit',
      function (e) {
        const form = e.target;
        if (!form || form.tagName !== 'FORM') return;

        const method = (form.method || 'GET').toUpperCase();
        if (method !== 'POST') return;

        const action = form.action || window.location.href;

        // Skip login and logout forms
        if (
          action.includes('/login') ||
          action.includes('/logout') ||
          form.getAttribute('data-no-offline') === 'true'
        ) {
          return;
        }

        // Check if offline
        if (isDeviceOffline()) {
          // SYNCHRONOUSLY STOP NAVIGATION IMMEDIATELY
          e.preventDefault();
          e.stopPropagation();
          e.stopImmediatePropagation();

          // Process queuing
          handleOfflineFormSubmit(form, action);
          return false;
        }
      },
      true // Capture phase
    );
  }

  // Universal Sync Triggers (covers iOS Safari where Background Sync is unavailable)
  if (typeof window !== 'undefined') {
    window.addEventListener('online', () => {
      processOutbox();
    });

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        processOutbox();
      }
    });

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'SYNC_OUTBOX_TRIGGER') {
          processOutbox();
        }
      });
    }

    // Auto-sync on page load if device is online
    if (typeof navigator !== 'undefined' && navigator.onLine) {
      setTimeout(() => { processOutbox(); }, 1000);
    }

    // Periodic auto-sync check every 30 seconds if online and pending items exist
    setInterval(() => {
      if (typeof navigator !== 'undefined' && navigator.onLine) {
        getPendingCount().then((count) => {
          if (count > 0) processOutbox();
        });
      }
    }, 30000);

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', attachUniversalOfflineFormInterceptor);
    } else {
      attachUniversalOfflineFormInterceptor();
    }
  }

  return {
    queueOrSend,
    processOutbox,
    getPendingCount,
    getPendingItems,
    getAllRecords,
    getFailedItems,
    retryFailedItem,
    retryAllFailed,
    discardItem,
    discardAllFailed,
    deleteRecord,
    enqueue: queueOrSend,
    dataURLtoFile,
  };
});
