/**
 * lib/jobs/dispatcher.js — Job_Dispatcher (비동기 job 생성·실행·상태 전이)
 *
 * Spec: .kiro/specs/mcp-tool-optimization/ (Task 16.2, design "Job_Dispatcher")
 *
 * 장시간 작업(`regenerate_stale_hdd`, reindex 등)을 동기 블로킹에서
 * "즉시 job 핸들 반환 + 백그라운드 실행"으로 전환한다(Req 5.1, 5.2).
 *
 *   createJob(type, payload, runner) -> { job_id, status_uri }
 *     1) job_id = crypto.randomUUID()
 *     2) store.put({ job_id, type, status: "queued", created_at, updated_at })  (Req 5.3)
 *     3) 백그라운드 실행 시작 — runJob() 을 await 하지 않는다 (Req 5.1, 5.2)
 *     4) status_uri = buildUri("job", job_id) => "job://<job_id>"               (Req 5.5)
 *     5) { job_id, status_uri } 를 즉시(non-blocking) 반환
 *
 *   runJob(job, runner, payload):
 *     store.update(job_id, status="running")                                    (Req 5.4)
 *     try   { result = await runner(payload); update(status="done", result) }   (Req 5.7)
 *     catch { update(status="failed", error) }                                  (Req 5.8)
 *
 * 상태는 항상 { queued, running, done, failed } 중 정확히 하나다(Req 5.4).
 *
 * 주입 가능(injectable) 설계:
 *   - `store` 는 createDispatcher({ store }) 로 주입한다(기본: defaultStore).
 *     테스트는 createInMemoryStore() 를 주입해 DynamoDB 없이 검증한다.
 *   - `runner` 는 createJob 의 인자로 주입한다(job 마다 다른 작업).
 *     테스트는 지연/실패/제어 가능한 mock runner 를 주입한다.
 *   여기서 실제 AWS/Lambda/네트워크 호출은 하지 않는다 — 순수 dispatch 로직만.
 *
 * 식별자-free: job 레코드는 user/team/corpus 필드를 담지 않는다.
 *
 * CommonJS — server.js와 동일.
 */

const crypto = require("node:crypto");

const { buildUri } = require("../uri");
const { JOB_STATUS, defaultStore } = require("./store");

/**
 * runJob(store, job_id, runner, payload) -> Promise<void>
 *
 * job 을 running 으로 전이한 뒤 runner(payload) 를 await 한다.
 * 성공하면 done(result), 던지면 failed(error message) 로 전이한다.
 * 이 함수 자체는 절대 reject 하지 않는다(백그라운드 실행이므로
 * unhandled rejection 을 만들지 않는다).
 */
async function runJob(store, job_id, runner, payload) {
  store.update(job_id, {
    status: JOB_STATUS.RUNNING,
    updated_at: new Date().toISOString(),
  });

  try {
    const result = await runner(payload);
    store.update(job_id, {
      status: JOB_STATUS.DONE,
      result: result === undefined ? null : result,
      updated_at: new Date().toISOString(),
    });
  } catch (err) {
    const message =
      err && typeof err.message === "string" && err.message.length > 0
        ? err.message
        : String(err);
    store.update(job_id, {
      status: JOB_STATUS.FAILED,
      error: message,
      updated_at: new Date().toISOString(),
    });
  }
}

/**
 * createDispatcher({ store }) -> { createJob, runJob }
 *
 * store 를 클로저로 캡처한 dispatcher 인스턴스를 만든다.
 * store 를 생략하면 공유 defaultStore 를 사용한다.
 */
function createDispatcher(options = {}) {
  const store = options.store || defaultStore;

  /**
   * createJob(type, payload, runner) -> { job_id, status_uri }
   *
   * 비블로킹: runner 의 소요 시간과 무관하게 즉시 핸들을 반환한다(Req 5.1, 5.2).
   * runner 는 payload 를 받아 Promise(또는 값)를 반환하는 함수여야 한다.
   */
  function createJob(type, payload, runner) {
    if (typeof runner !== "function") {
      throw new TypeError("createJob requires a runner function");
    }

    const job_id = crypto.randomUUID();
    const now = new Date().toISOString();

    // 1) 초기 queued 레코드 기록 (Req 5.3).
    store.put({
      job_id,
      type,
      status: JOB_STATUS.QUEUED,
      created_at: now,
      updated_at: now,
    });

    // 2) 백그라운드 실행 시작 — await 하지 않는다 (Req 5.1, 5.2).
    //    runJob 은 reject 하지 않지만, 방어적으로 catch 를 달아
    //    어떤 경우에도 unhandled rejection 이 발생하지 않게 한다.
    Promise.resolve()
      .then(() => runJob(store, job_id, runner, payload))
      .catch(() => {
        /* runJob 은 내부적으로 모든 에러를 흡수한다; 안전망 */
      });

    // 3) job:// 상태 URI 와 함께 즉시 반환 (Req 5.5).
    return {
      job_id,
      status_uri: buildUri("job", job_id),
    };
  }

  return { createJob, runJob };
}

// 기본 dispatcher — 공유 defaultStore 를 사용한다.
const defaultDispatcher = createDispatcher();

module.exports = {
  createDispatcher,
  runJob,
  defaultDispatcher,
};
