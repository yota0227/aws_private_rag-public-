/**
 * lib/jobs/store.js — Job 상태 저장소 추상화 (storage-agnostic)
 *
 * Spec: .kiro/specs/mcp-tool-optimization/ (Task 16.1, design "Job 상태 저장소")
 *
 * 비동기 Job 프레임워크(dispatcher, Task 16.2)와 `rag_task_status`(Task 16.5)가
 * job 레코드를 읽고 쓰는 단일 인터페이스를 제공한다. 인터페이스는 저장소 무관:
 *
 *   put(job)              // 신규 job 기록 (persist)
 *   get(job_id)           // 없으면 null → 호출부에서 not_found 로 변환
 *   update(job_id, patch) // 부분 갱신(status/result/error/updated_at), 없으면 null
 *
 * ──────────────────────────────────────────────────────────────────────────
 * OPEN QUESTION (OQ-2, design Open Question 2 — 아직 미결):
 *   영속 백엔드 선택은 미정이다.
 *     (a) 신규 DynamoDB 테이블 `bos-ai-mcp-jobs`, 또는
 *     (b) 기존 claim DB 테이블(`bos-ai-claim-db-prod`)에 job 레코드 타입 추가.
 *   결정이 내려지면 동일한 put/get/update 인터페이스 뒤에서 백엔드만 교체한다
 *   (핸들러·dispatcher 코드 불변). 아래의 in-memory 구현은 그때까지의
 *   swappable default 이며, dispatcher(16.2)와 테스트가 DynamoDB 없이
 *   동작하게 한다. 여기서 실제 AWS/네트워크 호출은 하지 않는다.
 * ──────────────────────────────────────────────────────────────────────────
 *
 * Job 레코드 스키마(design "Job 레코드"):
 *   {
 *     job_id:     string (uuid),
 *     type:       "regenerate_stale_hdd" | "reindex" | ...,
 *     status:     "queued" | "running" | "done" | "failed",
 *     created_at: ISO8601 string,
 *     updated_at: ISO8601 string,
 *     result?:    object,  // status=done 일 때
 *     error?:     string   // status=failed 일 때
 *   }
 *
 * 식별자-free: job 레코드는 user/team/corpus 필드를 일절 담지 않는다.
 *
 * CommonJS — server.js와 동일.
 */

// Job 상태 상수 (닫힌 4개 집합).
const JOB_STATUS = Object.freeze({
  QUEUED: "queued",
  RUNNING: "running",
  DONE: "done",
  FAILED: "failed",
});

// 부분 갱신(update)으로 허용되는 필드 화이트리스트.
// job_id/type/created_at 은 불변이므로 patch 로 덮어쓰지 않는다.
const UPDATABLE_FIELDS = ["status", "result", "error", "updated_at"];

/**
 * 레코드의 얕은 복사본을 반환한다.
 * 저장소 내부 상태가 호출부의 참조 변형으로 오염되지 않도록 격리한다.
 */
function cloneJob(job) {
  return { ...job };
}

/**
 * createInMemoryStore() -> { put, get, update }
 *
 * Map 기반 in-memory 구현. 프로세스 수명 동안만 유지되며 영속성은 없다.
 * 위 OQ-2 가 해소되면 동일 인터페이스로 DynamoDB/claim-DB 어댑터로 교체된다.
 */
function createInMemoryStore() {
  const jobs = new Map();

  /**
   * put(job): 신규 job 레코드를 기록한다.
   * 저장된(복사된) 레코드를 반환한다.
   */
  function put(job) {
    if (!job || typeof job.job_id !== "string" || job.job_id.length === 0) {
      throw new TypeError("store.put requires a job with a non-empty job_id");
    }
    const record = cloneJob(job);
    jobs.set(record.job_id, record);
    return cloneJob(record);
  }

  /**
   * get(job_id) -> job 레코드 복사본 | null
   * 부재 시 null 을 반환한다(호출부가 not_found 로 변환).
   */
  function get(job_id) {
    const record = jobs.get(job_id);
    return record ? cloneJob(record) : null;
  }

  /**
   * update(job_id, patch) -> 갱신된 레코드 복사본 | null
   * 화이트리스트 필드(status/result/error/updated_at)만 부분 적용한다.
   * job_id 가 없으면 null 을 반환한다(호출부가 not_found 로 변환).
   */
  function update(job_id, patch) {
    const record = jobs.get(job_id);
    if (!record) return null;

    const next = cloneJob(record);
    if (patch && typeof patch === "object") {
      for (const field of UPDATABLE_FIELDS) {
        if (Object.prototype.hasOwnProperty.call(patch, field)) {
          next[field] = patch[field];
        }
      }
    }
    jobs.set(job_id, next);
    return cloneJob(next);
  }

  return { put, get, update };
}

// 기본 싱글턴 저장소 — dispatcher/도구가 require 하여 공유한다.
// (백엔드 교체 시 이 export 만 새 어댑터 인스턴스로 바꾸면 된다.)
const defaultStore = createInMemoryStore();

module.exports = {
  JOB_STATUS,
  UPDATABLE_FIELDS,
  createInMemoryStore,
  defaultStore,
};
