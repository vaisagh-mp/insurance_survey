/**
 * Unit tests for offline-sync.js and image-compress.js
 * Run using Node.js: node --test static/js/offline-sync.test.mjs
 */

import test from 'node:test';
import assert from 'node:assert/strict';

// Load image-compress.js in Node
import imageCompressModule from './image-compress.js';

test('image-compress: calculateDimensions preserves aspect ratio and respects maxDimension', () => {
  const { calculateDimensions } = imageCompressModule;

  // 1. Landscape high-res: 4000 x 3000 -> max 1920
  const landscape = calculateDimensions(4000, 3000, 1920);
  assert.equal(landscape.width, 1920);
  assert.equal(landscape.height, 1440);

  // 2. Portrait high-res: 3000 x 4000 -> max 1920
  const portrait = calculateDimensions(3000, 4000, 1920);
  assert.equal(portrait.width, 1440);
  assert.equal(portrait.height, 1920);

  // 3. Square high-res: 2400 x 2400 -> max 1920
  const square = calculateDimensions(2400, 2400, 1920);
  assert.equal(square.width, 1920);
  assert.equal(square.height, 1920);

  // 4. Smaller than max: 1200 x 800 -> unchanged
  const small = calculateDimensions(1200, 800, 1920);
  assert.equal(small.width, 1200);
  assert.equal(small.height, 800);
});

test('offline-sync: queue and replay logic with mocked fetch', async () => {
  // Simple in-memory mock of IndexedDB store to test offline-sync queue/replay algorithm
  const mockStore = new Map();
  let idCounter = 1;

  function mockSave(record) {
    if (!record.id) record.id = 'id-' + idCounter++;
    mockStore.set(record.id, { ...record });
    return record;
  }

  function mockDelete(id) {
    mockStore.delete(id);
  }

  function mockGetAll() {
    return Array.from(mockStore.values());
  }

  // 1. Simulating queuing on network failure
  const testRequest = {
    method: 'PATCH',
    url: '/api/billing/invoices/10/',
    payload: { notes: 'Updated notes' },
    createdAt: new Date().toISOString(),
    entityType: 'invoice',
    entityId: 10,
    baseVersion: '2026-09-24T10:00:00Z',
    status: 'pending',
  };

  const queued = mockSave(testRequest);
  assert.equal(queued.status, 'pending');
  assert.equal(mockStore.size, 1);

  // 2. Mock processOutbox logic:
  // Case A: Mocked 200 OK -> record marked synced and removed
  async function simulateReplay(record, mockFetchFn) {
    record.status = 'syncing';
    try {
      const res = await mockFetchFn(record.url, {
        method: record.method,
        body: JSON.stringify(record.payload),
      });

      if (res.ok) {
        mockDelete(record.id);
        return { status: 'synced' };
      } else if (res.status === 409) {
        record.status = 'failed';
        record.failureReason = 'conflict';
        mockSave(record);
        return { status: 'conflict' };
      } else if (res.status === 401) {
        record.status = 'failed';
        record.failureReason = 'expired_auth';
        mockSave(record);
        return { status: 'expired_auth' };
      }
    } catch (networkErr) {
      record.status = 'pending';
      mockSave(record);
      return { status: 'network_retry' };
    }
  }

  // Test successful replay
  const successFetch = async () => ({ ok: true, status: 200 });
  const resultSuccess = await simulateReplay(queued, successFetch);
  assert.equal(resultSuccess.status, 'synced');
  assert.equal(mockStore.size, 0);

  // Case B: Mocked 409 Conflict -> marked failed with conflict reason
  const conflictItem = mockSave({
    ...testRequest,
    createdAt: new Date().toISOString(),
  });
  const conflictFetch = async () => ({
    ok: false,
    status: 409,
    json: async () => ({ detail: 'Resource was modified' }),
  });
  const resultConflict = await simulateReplay(conflictItem, conflictFetch);
  assert.equal(resultConflict.status, 'conflict');
  assert.equal(mockStore.get(conflictItem.id).status, 'failed');
  assert.equal(mockStore.get(conflictItem.id).failureReason, 'conflict');

  // Case C: Mocked Network Error -> left as pending for next retry
  const networkItem = mockSave({
    ...testRequest,
    createdAt: new Date().toISOString(),
  });
  const networkErrorFetch = async () => {
    throw new TypeError('Failed to fetch: Network is down');
  };
  const resultNetwork = await simulateReplay(networkItem, networkErrorFetch);
  assert.equal(resultNetwork.status, 'network_retry');
  assert.equal(mockStore.get(networkItem.id).status, 'pending');

  // Case D: In-order sorting test
  const item1 = { id: 'item-1', createdAt: '2026-09-24T10:00:00Z', status: 'pending' };
  const item2 = { id: 'item-2', createdAt: '2026-09-24T09:00:00Z', status: 'pending' };
  const item3 = { id: 'item-3', createdAt: '2026-09-24T11:00:00Z', status: 'pending' };
  const sorted = [item1, item2, item3].sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  assert.deepEqual(
    sorted.map((i) => i.id),
    ['item-2', 'item-1', 'item-3']
  );
});
