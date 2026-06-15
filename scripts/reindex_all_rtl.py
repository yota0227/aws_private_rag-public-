"""
Trigger RTL Parser Lambda for all RTL files in S3 bucket.
Uses direct Lambda invoke (InvocationType=Event, async) for parallel processing.

Usage:
    py scripts/reindex_all_rtl.py --pipeline-id tt_20260221 --batch-size 50
"""
import argparse
import json
import time
import sys
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed

BUCKET = "bos-ai-rtl-src-533335672315"
PREFIX_TEMPLATE = "rtl-sources/{pipeline_id}/"
LAMBDA_NAME = "lambda-rtl-parser-seoul-dev"
REGION = "ap-northeast-2"
RTL_EXTENSIONS = (".sv", ".v", ".svh", ".vh",
                  ".json", ".svd", ".h", ".hpp", ".c", ".cpp",
                  ".md", ".rst", ".txt", ".sdc", ".dts", ".csv",
                  ".py", ".tcl", ".yaml", ".yml", ".f")


def list_rtl_files(s3, bucket, prefix):
    """List all RTL files in S3 with the given prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    files = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(RTL_EXTENSIONS):
                files.append(key)
    return files


def invoke_lambda(lambda_client, bucket, key):
    """Invoke Lambda async with S3 event payload."""
    payload = {
        "Records": [{
            "s3": {
                "bucket": {"name": bucket},
                "object": {"key": key}
            }
        }]
    }
    try:
        lambda_client.invoke(
            FunctionName=LAMBDA_NAME,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        return (key, True, None)
    except Exception as e:
        return (key, False, str(e))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-id", default="tt_20260221")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Concurrent invocations per batch")
    parser.add_argument("--batch-delay", type=float, default=2.0,
                        help="Seconds to wait between batches")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start-at", type=int, default=0,
                        help="Skip first N files (for resuming)")
    args = parser.parse_args()

    s3 = boto3.client("s3", region_name=REGION)
    lambda_client = boto3.client("lambda", region_name=REGION)

    prefix = PREFIX_TEMPLATE.format(pipeline_id=args.pipeline_id)
    print(f"Listing files in s3://{BUCKET}/{prefix}...")
    files = list_rtl_files(s3, BUCKET, prefix)
    print(f"Found {len(files)} RTL files")

    if args.start_at > 0:
        files = files[args.start_at:]
        print(f"Skipping first {args.start_at}, processing {len(files)} remaining")

    if args.dry_run:
        print("[DRY RUN] First 5 files:")
        for f in files[:5]:
            print(f"  {f}")
        return

    success = 0
    failed = 0
    started_at = time.time()

    for batch_num, i in enumerate(range(0, len(files), args.batch_size)):
        batch = files[i:i + args.batch_size]
        with ThreadPoolExecutor(max_workers=args.batch_size) as executor:
            futures = [executor.submit(invoke_lambda, lambda_client, BUCKET, key)
                       for key in batch]
            for future in as_completed(futures):
                key, ok, err = future.result()
                if ok:
                    success += 1
                else:
                    failed += 1
                    print(f"  FAIL: {key} - {err}", file=sys.stderr)

        elapsed = time.time() - started_at
        processed = args.start_at + success + failed
        total = args.start_at + len(files)
        rate = (success + failed) / elapsed if elapsed > 0 else 0
        remaining = (len(files) - success - failed) / rate if rate > 0 else 0
        print(f"Batch {batch_num + 1}: {processed}/{total} triggered "
              f"(success={success}, failed={failed}, "
              f"rate={rate:.1f}/s, ETA={remaining/60:.1f}min)")

        if i + args.batch_size < len(files):
            time.sleep(args.batch_delay)

    print(f"\nDone: {success} succeeded, {failed} failed")
    print(f"Total time: {(time.time() - started_at)/60:.1f} min")
    print("\nNote: Lambda invocations are async. Actual parsing may take "
          "longer. Check CloudWatch logs for completion.")


if __name__ == "__main__":
    main()
