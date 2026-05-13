"""
Bulk approve claims in DynamoDB for HDD generation.

Sets status='verified' and approval_status='approved' for all claims
matching the specified topic(s) and pipeline_id.

Usage:
    py scripts/bulk_approve_claims.py --pipeline-id tt_20260221 --topics NoC,EDC,Overlay,Dispatch
    py scripts/bulk_approve_claims.py --pipeline-id tt_20260221 --all-topics
    py scripts/bulk_approve_claims.py --pipeline-id tt_20260221 --all-topics --dry-run
"""
import argparse
import json
import time
import sys
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

CLAIM_DB_TABLE = "bos-ai-claim-db-dev"
REGION = "ap-northeast-2"


def get_claims_by_topic(table, topic, pipeline_id=None):
    """Query claims by topic using GSI."""
    try:
        kwargs = {
            "IndexName": "topic-index",
            "KeyConditionExpression": Key("topic").eq(topic),
        }
        if pipeline_id:
            kwargs["FilterExpression"] = Attr("pipeline_id").eq(pipeline_id)

        items = []
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))

        while "LastEvaluatedKey" in response:
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.query(**kwargs)
            items.extend(response.get("Items", []))

        return items
    except Exception as e:
        print(f"  Error querying topic '{topic}': {e}", file=sys.stderr)
        return []


def get_all_topics(table, pipeline_id=None):
    """Scan for distinct topics in the table."""
    topics = set()
    scan_kwargs = {}
    if pipeline_id:
        scan_kwargs["FilterExpression"] = Attr("pipeline_id").eq(pipeline_id)
    scan_kwargs["ProjectionExpression"] = "topic"

    response = table.scan(**scan_kwargs)
    for item in response.get("Items", []):
        if item.get("topic"):
            topics.add(item["topic"])

    while "LastEvaluatedKey" in response:
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            if item.get("topic"):
                topics.add(item["topic"])

    return sorted(topics)


def approve_claim(table, claim):
    """Update a single claim to verified+approved status."""
    claim_id = claim.get("claim_id")
    version = claim.get("version", 1)
    now = datetime.now(timezone.utc).isoformat()

    try:
        table.update_item(
            Key={"claim_id": claim_id, "version": int(version)},
            UpdateExpression=(
                "SET #s = :verified, "
                "approval_status = :approved, "
                "approved_by = :by, "
                "approved_at = :at, "
                "last_verified_at = :at"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":verified": "verified",
                ":approved": "approved",
                ":by": "system:bulk_approve",
                ":at": now,
            },
        )
        return True
    except Exception as e:
        print(f"  Error approving {claim_id}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Bulk approve claims for HDD generation")
    parser.add_argument("--pipeline-id", default="tt_20260221")
    parser.add_argument("--topics", help="Comma-separated topic list (e.g., NoC,EDC,Overlay)")
    parser.add_argument("--all-topics", action="store_true", help="Approve all topics")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(CLAIM_DB_TABLE)

    if args.all_topics:
        print(f"Scanning all topics for pipeline_id={args.pipeline_id}...")
        topics = get_all_topics(table, args.pipeline_id)
        print(f"Found {len(topics)} topics: {', '.join(topics[:20])}{'...' if len(topics) > 20 else ''}")
    elif args.topics:
        topics = [t.strip() for t in args.topics.split(",")]
    else:
        print("Error: specify --topics or --all-topics", file=sys.stderr)
        return 1

    total_approved = 0
    total_skipped = 0
    total_failed = 0

    for topic in topics:
        claims = get_claims_by_topic(table, topic, args.pipeline_id)
        need_approval = [
            c for c in claims
            if c.get("approval_status") != "approved" or c.get("status") != "verified"
        ]

        if not need_approval:
            print(f"  [{topic}] {len(claims)} claims, all already approved")
            total_skipped += len(claims)
            continue

        print(f"  [{topic}] {len(claims)} claims, {len(need_approval)} need approval")

        if args.dry_run:
            total_skipped += len(need_approval)
            continue

        for claim in need_approval:
            if approve_claim(table, claim):
                total_approved += 1
            else:
                total_failed += 1

        # Rate limiting to avoid DynamoDB throttling
        time.sleep(0.5)

    print(f"\nDone: {total_approved} approved, {total_skipped} skipped, {total_failed} failed")
    if args.dry_run:
        print("[DRY RUN] No changes made")
    return 0


if __name__ == "__main__":
    sys.exit(main())
