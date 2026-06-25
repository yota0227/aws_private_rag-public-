// Property tests for lib/jobs/dispatcher.js — Job_Dispatcher
//
// Spec: .kiro/specs/mcp-tool-optimization/ (Task 16.3, 16.4 + Properties 22, 23)
// Runner: node:test ; Property library: fast-check (numRuns >= 100).
//
// 실제 AWS/Lambda/네트워크 없이 in-memory store + 주입된 mock runner 로
// dispatch 로직만 검증한다. 비블로킹(22)은 지연 runner 로, lifecycle(23)은
// 해소 시점을 직접 제어하는 runner 로 중간 상태를 관측한다.

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fc = require("fast-check");

const { createDispatcher } = require("../lib/jobs/dispatcher");
const { createInMemoryStore, JOB_STATUS } = require("../lib/jobs/store");
const { isWellFormed, parseUri } = require("../lib/uri");

const NUM_RUNS = 100;

// Promise/microtask·timer 큐가 모두 비워질 때까지 양보한다.
// 백그라운드 runJob 의 상태 전이가 store 에 반영될 시간을 준다.
function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

// 외부에서 해소 시점을 제어할 수 있는 deferred runner 를 만든다.
function makeControllableRunner() {
  let resolveFn;
  let rejectFn;
  const gate = new Promise((resolve, reject) => {
    resolveFn = resolve;
    rejectFn = reject;
  });
  const runner = () => gate;
  return { runner, resolve: resolveFn, reject: rejectFn };
}

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 22: Job 디스패치 비블로킹
// Validates: Requirements 5.1, 5.2
// ---------------------------------------------------------------------------
test("Property 22: createJob은 runner 소요시간과 무관하게 즉시 job_id + job:// URI를 반환한다", async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.constantFrom("regenerate_stale_hdd", "reindex"),
      // runner 가 완료까지 걸리는 (모사) 지연. 실제로 기다리지 않음을 검증.
      fc.integer({ min: 50, max: 5000 }),
      async (type, runnerDelayMs) => {
        const store = createInMemoryStore();
        const dispatcher = createDispatcher({ store });

        let runnerCompleted = false;
        // 지연 후에야 완료되는 runner.
        const runner = () =>
          new Promise((resolve) => {
            setTimeout(() => {
              runnerCompleted = true;
              resolve({ ok: true });
            }, runnerDelayMs);
          });

        const before = Date.now();
        const handle = dispatcher.createJob(type, { any: "payload" }, runner);
        const dispatchMs = Date.now() - before;

        // 즉시 반환: runner 가 끝나기 한참 전에(그리고 매우 빠르게) 핸들을 받는다.
        assert.ok(
          dispatchMs < runnerDelayMs,
          `dispatch(${dispatchMs}ms)는 runner 지연(${runnerDelayMs}ms)보다 빨라야 한다`
        );
        // runner 는 아직 완료되지 않았다(비블로킹).
        assert.equal(runnerCompleted, false);

        // 반환 핸들: job_id + well-formed job:// 상태 URI.
        assert.equal(typeof handle.job_id, "string");
        assert.ok(handle.job_id.length > 0);
        assert.equal(handle.status_uri, `job://${handle.job_id}`);
        assert.ok(isWellFormed(handle.status_uri));
        // status_uri 를 parse 하면 동일 job_id 가 복원된다(rag_task_status 해석 가능).
        assert.equal(parseUri(handle.status_uri).id, handle.job_id);

        // 생성 직후 상태는 queued (아직 결과 없음).
        const initial = store.get(handle.job_id);
        assert.ok(initial);
        assert.equal(initial.status, JOB_STATUS.QUEUED);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 23: Job lifecycle 일관성
// Validates: Requirements 4.6, 5.3, 5.4, 5.6, 5.7, 5.8
// ---------------------------------------------------------------------------
const VALID_STATUSES = new Set([
  JOB_STATUS.QUEUED,
  JOB_STATUS.RUNNING,
  JOB_STATUS.DONE,
  JOB_STATUS.FAILED,
]);

test("Property 23: 성공 job은 queued→running→done(result)로 전이하며 매 시점 상태가 4개 중 하나다", async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.constantFrom("regenerate_stale_hdd", "reindex"),
      fc.record({ sections: fc.integer({ min: 0, max: 99 }) }),
      async (type, resultPayload) => {
        const store = createInMemoryStore();
        const dispatcher = createDispatcher({ store });
        const { runner, resolve } = makeControllableRunner();

        const { job_id } = dispatcher.createJob(type, null, runner);

        // 생성 직후: queued, 최종 결과 없음 (Req 5.3, 5.6).
        let rec = store.get(job_id);
        assert.equal(rec.status, JOB_STATUS.QUEUED);
        assert.ok(VALID_STATUSES.has(rec.status));
        assert.equal(rec.result, undefined);

        // 백그라운드가 running 으로 전이할 시간을 준다 (Req 5.4).
        await flush();
        rec = store.get(job_id);
        assert.equal(rec.status, JOB_STATUS.RUNNING);
        assert.ok(VALID_STATUSES.has(rec.status));
        // running 동안 polling: 최종 결과 없음 (Req 5.6).
        assert.equal(rec.result, undefined);

        // runner 를 성공 해소 → done + result (Req 5.7).
        resolve(resultPayload);
        await flush();
        rec = store.get(job_id);
        assert.equal(rec.status, JOB_STATUS.DONE);
        assert.ok(VALID_STATUSES.has(rec.status));
        assert.deepEqual(rec.result, resultPayload);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 23: 실패 job은 running→failed(error)로 전이하며 에러 표시를 담는다", async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.constantFrom("regenerate_stale_hdd", "reindex"),
      fc.string({ minLength: 1, maxLength: 60 }),
      async (type, errMessage) => {
        const store = createInMemoryStore();
        const dispatcher = createDispatcher({ store });
        const { runner, reject } = makeControllableRunner();

        const { job_id } = dispatcher.createJob(type, null, runner);

        // queued → running.
        await flush();
        let rec = store.get(job_id);
        assert.equal(rec.status, JOB_STATUS.RUNNING);

        // runner 실패 → failed + error 표시 (Req 5.8).
        reject(new Error(errMessage));
        await flush();
        rec = store.get(job_id);
        assert.equal(rec.status, JOB_STATUS.FAILED);
        assert.ok(VALID_STATUSES.has(rec.status));
        assert.equal(rec.error, errMessage);
        // 실패 시 result 는 없다.
        assert.equal(rec.result, undefined);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 23: 완료된 job의 상태는 항상 4개 닫힌 집합 중 하나다 (성공/실패 무관)", async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.boolean(),
      fc.integer({ min: 0, max: 5 }),
      async (shouldSucceed, delayMs) => {
        const store = createInMemoryStore();
        const dispatcher = createDispatcher({ store });

        const runner = () =>
          new Promise((resolve, reject) => {
            setTimeout(() => {
              if (shouldSucceed) resolve({ done: true });
              else reject(new Error("boom"));
            }, delayMs);
          });

        const { job_id } = dispatcher.createJob("reindex", null, runner);

        // 완료될 때까지 폴링하며, 매 관측 시점의 상태가 유효 집합에 속하는지 확인.
        let rec = store.get(job_id);
        assert.ok(VALID_STATUSES.has(rec.status));

        for (
          let i = 0;
          i < 50 &&
          rec.status !== JOB_STATUS.DONE &&
          rec.status !== JOB_STATUS.FAILED;
          i++
        ) {
          await flush();
          rec = store.get(job_id);
          assert.ok(VALID_STATUSES.has(rec.status));
        }

        assert.equal(
          rec.status,
          shouldSucceed ? JOB_STATUS.DONE : JOB_STATUS.FAILED
        );
      }
    ),
    { numRuns: NUM_RUNS }
  );
});
