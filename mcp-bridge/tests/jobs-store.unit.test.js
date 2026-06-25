// Feature: mcp-tool-optimization, Task 16.1 unit test — lib/jobs/store.js
//
// Job 상태 저장소(in-memory default)의 put/get/update 동작과
// 부재 시 null 반환 계약을 검증한다. (job lifecycle 속성 22/23 은
// dispatcher 와 함께 16.2~16.4 에서 별도 검증.)

const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  JOB_STATUS,
  createInMemoryStore,
  defaultStore,
} = require('../lib/jobs/store');

function sampleJob(overrides = {}) {
  const now = new Date().toISOString();
  return {
    job_id: 'job-123',
    type: 'regenerate_stale_hdd',
    status: JOB_STATUS.QUEUED,
    created_at: now,
    updated_at: now,
    ...overrides,
  };
}

test('put then get returns the stored job record', () => {
  const store = createInMemoryStore();
  const job = sampleJob();
  store.put(job);

  const fetched = store.get('job-123');
  assert.ok(fetched, 'job should be retrievable');
  assert.equal(fetched.job_id, 'job-123');
  assert.equal(fetched.type, 'regenerate_stale_hdd');
  assert.equal(fetched.status, JOB_STATUS.QUEUED);
});

test('get on a missing job_id returns null', () => {
  const store = createInMemoryStore();
  assert.equal(store.get('does-not-exist'), null);
});

test('update applies a partial patch and returns the updated record', () => {
  const store = createInMemoryStore();
  store.put(sampleJob());

  const updated = store.update('job-123', {
    status: JOB_STATUS.DONE,
    result: { sections: 3 },
    updated_at: '2026-06-16T00:00:00.000Z',
  });

  assert.ok(updated);
  assert.equal(updated.status, JOB_STATUS.DONE);
  assert.deepEqual(updated.result, { sections: 3 });
  assert.equal(updated.updated_at, '2026-06-16T00:00:00.000Z');
  // immutable fields preserved
  assert.equal(updated.job_id, 'job-123');
  assert.equal(updated.type, 'regenerate_stale_hdd');

  // persisted: a subsequent get reflects the update
  assert.equal(store.get('job-123').status, JOB_STATUS.DONE);
});

test('update ignores non-whitelisted fields (job_id/type/created_at immutable)', () => {
  const store = createInMemoryStore();
  store.put(sampleJob({ created_at: '2026-01-01T00:00:00.000Z' }));

  const updated = store.update('job-123', {
    job_id: 'hacked',
    type: 'reindex',
    created_at: '1999-01-01T00:00:00.000Z',
    status: JOB_STATUS.RUNNING,
  });

  assert.equal(updated.job_id, 'job-123');
  assert.equal(updated.type, 'regenerate_stale_hdd');
  assert.equal(updated.created_at, '2026-01-01T00:00:00.000Z');
  assert.equal(updated.status, JOB_STATUS.RUNNING);
});

test('update on a missing job_id returns null', () => {
  const store = createInMemoryStore();
  assert.equal(store.update('nope', { status: JOB_STATUS.FAILED }), null);
});

test('put returns a copy — external mutation does not corrupt the store', () => {
  const store = createInMemoryStore();
  const job = sampleJob();
  store.put(job);

  job.status = JOB_STATUS.FAILED; // mutate caller's reference after put
  assert.equal(store.get('job-123').status, JOB_STATUS.QUEUED);
});

test('put requires a non-empty job_id', () => {
  const store = createInMemoryStore();
  assert.throws(() => store.put({ type: 'reindex' }), TypeError);
  assert.throws(() => store.put({ job_id: '', type: 'reindex' }), TypeError);
});

test('defaultStore singleton exposes the put/get/update interface', () => {
  assert.equal(typeof defaultStore.put, 'function');
  assert.equal(typeof defaultStore.get, 'function');
  assert.equal(typeof defaultStore.update, 'function');
});
