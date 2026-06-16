"""Drain the RTL Parser DLQ, extract failed S3 keys, and re-invoke the parser.

The async RTL parser sends failed invocations to an SQS DLQ (on_failure).
After fixing parser bugs and redeploying, this script re-processes the
failed files so indexing reaches 100%.

Modes:
    --dry        : receive + parse messages, report key/pipeline/error breakdown.
                   Does NOT delete from the queue and does NOT re-invoke.
    (default)    : drain (receive + DELETE) matching messages, collect unique
                   keys, then re-invoke the parser Lambda (paced).

Filtering:
    --prefix     : only process S3 keys containing this substring
                   (default: rtl-sources/tt_20260516/). Non-matching drained
                   messages are left in the queue (not deleted).

Pacing (re-invoke): same model as reindex_all_rtl.py — reserved concurrency
on the Lambda caps cost; batch-size/batch-delay pace enqueue to drain rate.

Usage:
    py scripts/reprocess_dlq.py --dry
    py scripts/reprocess_dlq.py --prefix rtl-sources/tt_20260516/ --batch-size 5 --batch-delay 50
"""
import argparse
import json
import sys
import time

import boto3

REGION = "ap-northeast-2"
DLQ_URL = "https://sqs.ap-northeast-2.amazonaws.com/533335672315/rtl-parser-dlq"
LAMBDA_NAME = "lambda-rtl-parser-seoul-dev"
BUCKET = "bos-ai-rtl-src-533335672315"

# 세션 동안 이미 본 메시지가 다시 안 보이도록 충분히 긴 visibility (dry 모드에서 무한루프 방지)
VISIBILITY_TIMEOUT = 600


def _extract_key(body: str):
    """Extract the S3 object key from a DLQ message body (async failure record)."""
    try:
        doc = json.loads(body)
        records = doc.get("requestPayload", {}).get("Records", [])
        if records:
            return records[0].get("s3", {}).get("object", {}).get("key", "")
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        pass
    return ""


def _extract_error(body: str):
    """Extract a short error signature from the DLQ message body."""
    try:
        doc = json.loads(body)
        rp = doc.get("responsePayload", {})
        etype = rp.get("errorType", "")
        emsg = str(rp.get("errorMessage", ""))[:80]
        return f"{etype}: {emsg}".strip(": ")
    except (json.JSONDecodeError, TypeError):
        return "unparseable"


def drain(sqs, prefix, dry):
    """Receive messages; collect matching keys. In non-dry mode, delete matched.

    메시지 ID를 추적하여 새 메시지가 더 이상 안 보이면 종료한다 (재출현 무한루프 방지).
    Returns (unique_keys, error_counts, total_seen, matched_count).
    """
    unique_keys = set()
    error_counts = {}
    seen_ids = set()
    matched = 0
    no_new_polls = 0

    while no_new_polls < 5:
        resp = sqs.receive_message(
            QueueUrl=DLQ_URL,
            MaxNumberOfMessages=10,
            VisibilityTimeout=VISIBILITY_TIMEOUT,
            WaitTimeSeconds=2,
        )
        msgs = resp.get("Messages", [])
        new_in_poll = 0

        for m in msgs:
            mid = m.get("MessageId")
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            new_in_poll += 1

            body = m.get("Body", "")
            key = _extract_key(body)
            err = _extract_error(body)
            error_counts[err] = error_counts.get(err, 0) + 1
            if key and (not prefix or prefix in key):
                unique_keys.add(key)
                matched += 1
                if not dry:
                    sqs.delete_message(
                        QueueUrl=DLQ_URL,
                        ReceiptHandle=m["ReceiptHandle"],
                    )

        if new_in_poll == 0:
            no_new_polls += 1
        else:
            no_new_polls = 0

        if len(seen_ids) % 500 < 10 and len(seen_ids) > 0:
            print(f"  ...seen {len(seen_ids)} (matched {matched})", flush=True)

    return unique_keys, error_counts, len(seen_ids), matched


def invoke_lambda(lambda_client, key):
    payload = {"Records": [{"s3": {"bucket": {"name": BUCKET},
                                   "object": {"key": key}}}]}
    try:
        lambda_client.invoke(
            FunctionName=LAMBDA_NAME,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        return True
    except Exception as e:
        print(f"  FAIL invoke {key}: {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="rtl-sources/tt_20260516/")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--from-file", default=None,
                    help="드레인 대신 이 파일의 키 목록을 재invoke (dlq_reprocess_keys.txt)")
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--batch-delay", type=float, default=50.0)
    args = ap.parse_args()

    # --from-file: 이미 수집된 키 목록으로 바로 재invoke (DLQ 재드레인 생략)
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            keys_list = sorted({ln.strip() for ln in f if ln.strip()})
        print(f"Loaded {len(keys_list)} keys from {args.from_file}")
        if not keys_list:
            print("키 없음.")
            return
        lambda_client = boto3.client("lambda", region_name=REGION)
        success = 0
        for i in range(0, len(keys_list), args.batch_size):
            for k in keys_list[i:i + args.batch_size]:
                if invoke_lambda(lambda_client, k):
                    success += 1
            print(f"  re-invoked {min(i + args.batch_size, len(keys_list))}/{len(keys_list)}", flush=True)
            if i + args.batch_size < len(keys_list):
                time.sleep(args.batch_delay)
        print(f"\nDone: re-invoked {success}/{len(keys_list)} files.")
        return

    sqs = boto3.client("sqs", region_name=REGION)

    print(f"Draining DLQ (prefix filter: {args.prefix or 'ALL'}, dry={args.dry})...")
    keys, errors, total, matched = drain(sqs, args.prefix, args.dry)

    print("\n=== DLQ summary ===")
    print(f"unique messages seen: {total}")
    print(f"matched prefix: {matched}")
    print(f"unique keys to reprocess: {len(keys)}")
    print("\n=== error breakdown (top 15) ===")
    for err, cnt in sorted(errors.items(), key=lambda x: -x[1])[:15]:
        print(f"  {cnt:5d}  {err}")

    with open("dlq_reprocess_keys.txt", "w", encoding="utf-8") as f:
        for k in sorted(keys):
            f.write(k + "\n")
    print("\nkeys written to dlq_reprocess_keys.txt")

    if args.dry:
        print("[DRY] no deletion, no re-invoke.")
        return

    if not keys:
        print("재처리할 키 없음.")
        return

    lambda_client = boto3.client("lambda", region_name=REGION)
    keys_list = sorted(keys)
    success = 0
    for i in range(0, len(keys_list), args.batch_size):
        batch = keys_list[i:i + args.batch_size]
        for k in batch:
            if invoke_lambda(lambda_client, k):
                success += 1
        print(f"  re-invoked {min(i + args.batch_size, len(keys_list))}/{len(keys_list)}", flush=True)
        if i + args.batch_size < len(keys_list):
            time.sleep(args.batch_delay)

    print(f"\nDone: re-invoked {success}/{len(keys_list)} files.")


if __name__ == "__main__":
    main()
