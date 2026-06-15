"""
Load trinity_hierarchy.txt into Neptune via Lambda invoke.

PC -> Lambda(Seoul VPC) -> VPC Peering -> Neptune(Virginia)

Uses RTL Parser Lambda which has Neptune write IAM permission and
network path (Seoul VPC -> VPC Peering -> Virginia VPC port 8182).

Usage:
    py scripts/load_neptune_via_lambda.py --dry-run
    py scripts/load_neptune_via_lambda.py

NOTE: Requires /rag/neptune-load handler in Lambda code (index.py).
"""
import argparse
import json
import sys
import time

import boto3

LAMBDA_FUNCTION = "lambda-document-processor-seoul-prod"
LAMBDA_REGION = "ap-northeast-2"
NEPTUNE_ENDPOINT = "bos-ai-neptune-prod.cluster-c254guiq2xho.us-east-1.neptune.amazonaws.com"


def parse_hierarchy(filepath):
    """Parse hierarchy file into parent-child relationships.
    
    Special handling: modules that should be direct children of 'trinity'
    but appear nested due to RTL dump tool indentation quirks.
    """
    # Known UNIQUE direct children of 'trinity' that don't appear deeper in hierarchy
    # Only modules that are instantiated ONLY at trinity level (not reused inside sub-modules)
    TRINITY_DIRECT_CHILDREN = {
        'tt_tensix_with_l1', 'trinity_noc2axi_ne_opt',
        'trinity_noc2axi_nw_opt', 'trinity_noc2axi_router_ne_opt',
        'trinity_noc2axi_router_nw_opt', 'tt_dispatch_top_east',
        'tt_dispatch_top_west'
    }

    records = []
    stack = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            stripped = line.rstrip()
            indent = len(stripped) - len(stripped.lstrip())
            content = stripped.strip()

            if ":" not in content:
                continue

            parts = content.split(":", 1)
            module_name = parts[0].strip()
            instance_name = parts[1].strip()

            # Pop stack to correct depth
            while stack and stack[-1][0] >= indent:
                stack.pop()

            # Fix: if module is a known trinity direct child but appears nested
            # under tt_noc_repeaters, force parent to 'trinity'
            if module_name in TRINITY_DIRECT_CHILDREN and stack:
                # Find 'trinity' in stack and reset to that level
                trinity_idx = None
                for idx, (s_indent, s_inst, s_mod) in enumerate(stack):
                    if s_mod == 'trinity':
                        trinity_idx = idx
                        break
                if trinity_idx is not None:
                    stack = stack[:trinity_idx + 1]

            parent_module = stack[-1][2] if stack else None
            parent_instance = stack[-1][1] if stack else None
            depth = len(stack)

            records.append({
                "module_name": module_name,
                "instance_name": instance_name,
                "parent_module": parent_module,
                "parent_instance": parent_instance,
                "depth": depth,
            })

            stack.append((indent, instance_name, module_name))

    return records


def build_batches(records, batch_size=20):
    """Split records into batches for Lambda invocation."""
    modules = set()
    for r in records:
        modules.add(r["module_name"])
        if r["parent_module"]:
            modules.add(r["parent_module"])

    edges = []
    for r in records:
        if r["parent_module"]:
            edges.append({
                "parent": r["parent_module"],
                "child": r["module_name"],
                "instance_name": r["instance_name"],
                "depth": r["depth"],
            })

    batches = []

    # Module node batches
    module_list = sorted(modules)
    for i in range(0, len(module_list), batch_size):
        batch = module_list[i:i+batch_size]
        batches.append({
            "action": "create_nodes",
            "modules": batch,
        })

    # Edge batches
    for i in range(0, len(edges), batch_size):
        batch = edges[i:i+batch_size]
        batches.append({
            "action": "create_edges",
            "edges": batch,
        })

    return batches, len(modules), len(edges)


def invoke_lambda(client, batch, dry_run=False):
    """Invoke Lambda with Neptune graph load payload."""
    payload = {
        "httpMethod": "POST",
        "path": "/rag/neptune-load",
        "body": json.dumps({
            "neptune_endpoint": NEPTUNE_ENDPOINT,
            **batch,
        }),
    }

    if dry_run:
        return {"statusCode": 200, "body": json.dumps({"status": "dry-run"})}

    response = client.invoke(
        FunctionName=LAMBDA_FUNCTION,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode(),
    )

    resp_payload = json.loads(response["Payload"].read())
    return resp_payload


def main():
    parser = argparse.ArgumentParser(description="Load RTL hierarchy into Neptune via Lambda")
    parser.add_argument("--input", default="trinity_hierarchy.txt")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args()

    print(f"Parsing {args.input}...")
    records = parse_hierarchy(args.input)
    print(f"  {len(records)} hierarchy records")

    print(f"\nBuilding batches (size={args.batch_size})...")
    batches, n_modules, n_edges = build_batches(records, args.batch_size)
    print(f"  {n_modules} modules, {n_edges} edges, {len(batches)} batches")

    client = boto3.client("lambda", region_name=LAMBDA_REGION)

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Invoking Lambda: {LAMBDA_FUNCTION}")
    start = time.time()
    success = 0
    failed = 0

    for i, batch in enumerate(batches):
        try:
            result = invoke_lambda(client, batch, args.dry_run)

            if isinstance(result, dict) and result.get("statusCode") == 200:
                success += 1
            elif isinstance(result, dict) and "body" in result:
                body = json.loads(result["body"]) if isinstance(result["body"], str) else result["body"]
                if body.get("error"):
                    print(f"  [{i+1}/{len(batches)}] ERROR: {body['error']}", file=sys.stderr)
                    failed += 1
                else:
                    success += 1
            else:
                success += 1

            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(batches)}] {success} ok, {failed} failed")

        except Exception as e:
            print(f"  [{i+1}/{len(batches)}] EXCEPTION: {e}", file=sys.stderr)
            failed += 1

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s: {success} success, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
