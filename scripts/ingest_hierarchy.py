"""
Parse trinity_hierarchy.txt and ingest into DynamoDB Claim DB + (future) Neptune.

Input format: indentation-based hierarchy
    module_name: instance_name

Output:
1. JSON file (test_rtl/trinity_hierarchy.json) — structured hierarchy
2. DynamoDB claims — structural claims with topic="Hierarchy"

Usage:
    py scripts/ingest_hierarchy.py --input trinity_hierarchy.txt --dry-run
    py scripts/ingest_hierarchy.py --input trinity_hierarchy.txt --pipeline-id tt_20260221
"""
import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

CLAIM_DB_TABLE = "bos-ai-claim-db-dev"
REGION = "ap-northeast-2"


def parse_hierarchy_file(filepath: str) -> list[dict]:
    """Parse indentation-based hierarchy file into structured records.

    Returns list of dicts with:
        module_name, instance_name, depth, parent_instance, hier_path
    """
    records = []
    stack = []  # [(depth, instance_name, module_name)]

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            # Calculate depth from leading spaces
            stripped = line.rstrip()
            indent = len(stripped) - len(stripped.lstrip())
            content = stripped.strip()

            if ":" not in content:
                continue

            parts = content.split(":", 1)
            module_name = parts[0].strip()
            instance_name = parts[1].strip()

            # Pop stack to find parent at correct depth
            while stack and stack[-1][0] >= indent:
                stack.pop()

            parent_instance = stack[-1][1] if stack else ""
            parent_module = stack[-1][2] if stack else ""

            # Build hierarchy path
            if stack:
                hier_path = "/".join(s[1] for s in stack) + "/" + instance_name
            else:
                hier_path = instance_name

            records.append({
                "module_name": module_name,
                "instance_name": instance_name,
                "depth": len(stack),
                "parent_instance": parent_instance,
                "parent_module": parent_module,
                "hier_path": hier_path,
                "line_num": line_num,
            })

            stack.append((indent, instance_name, module_name))

    return records


def records_to_json(records: list[dict], output_path: str):
    """Save parsed records as JSON."""
    tree = {"root": "tb_trinity", "total_instances": len(records), "records": records}

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)

    print(f"JSON saved: {output_path} ({len(records)} records)")


def ingest_to_dynamodb(records: list[dict], pipeline_id: str, dry_run: bool = False):
    """Insert hierarchy records as structural claims into DynamoDB."""
    if dry_run:
        print(f"[DRY RUN] Would insert {len(records)} claims")
        for r in records[:5]:
            print(f"  {r['hier_path']} (module={r['module_name']})")
        return

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(CLAIM_DB_TABLE)

    now = datetime.now(timezone.utc).isoformat()
    success = 0
    failed = 0

    with table.batch_writer() as batch:
        for record in records:
            claim_text = (
                f"Module '{record['parent_module']}' instantiates "
                f"'{record['module_name']}' as '{record['instance_name']}'"
                if record['parent_module']
                else f"Top-level module '{record['module_name']}' instance '{record['instance_name']}'"
            )

            item = {
                "claim_id": str(uuid.uuid4()),
                "version": 1,
                "is_latest": True,
                "claim_text": claim_text,
                "claim_type": "structural",
                "topic": "Hierarchy",
                "module_name": record["module_name"],
                "file_path": f"hierarchy/{pipeline_id}/trinity_hierarchy.txt",
                "pipeline_id": pipeline_id,
                "parser_source": "hierarchy_ingest",
                "status": "verified",
                "approval_status": "approved",
                "approved_by": "system:hierarchy_ingest",
                "approved_at": now,
                "last_verified_at": now,
                "created_at": now,
                "created_by": "system:hierarchy_ingest",
                "instance_name": record["instance_name"],
                "parent_instance": record["parent_instance"],
                "parent_module": record["parent_module"],
                "hier_path": record["hier_path"],
                "hierarchy_depth": record["depth"],
            }

            try:
                batch.put_item(Item=item)
                success += 1
            except Exception as e:
                print(f"  Error: {e}", file=sys.stderr)
                failed += 1

    print(f"DynamoDB: {success} inserted, {failed} failed")


def main():
    parser = argparse.ArgumentParser(description="Ingest Trinity hierarchy into RAG system")
    parser.add_argument("--input", default="trinity_hierarchy.txt", help="Input hierarchy file")
    parser.add_argument("--output-json", default="test_rtl/trinity_hierarchy.json", help="Output JSON path")
    parser.add_argument("--pipeline-id", default="tt_20260221")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-dynamodb", action="store_true", help="Only generate JSON, skip DynamoDB")
    args = parser.parse_args()

    print(f"Parsing {args.input}...")
    records = parse_hierarchy_file(args.input)
    print(f"Parsed {len(records)} hierarchy records")

    # Save JSON
    records_to_json(records, args.output_json)

    # DynamoDB ingestion
    if not args.skip_dynamodb:
        print(f"\nIngesting to DynamoDB ({CLAIM_DB_TABLE})...")
        ingest_to_dynamodb(records, args.pipeline_id, args.dry_run)
    else:
        print("Skipping DynamoDB ingestion (--skip-dynamodb)")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
