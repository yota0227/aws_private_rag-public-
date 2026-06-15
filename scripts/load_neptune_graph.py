"""
Load trinity_hierarchy.txt into Neptune Graph DB as openCypher nodes/edges.

Creates:
- Module nodes (label: Module, properties: name, type)
- INSTANTIATES edges (parent -> child, properties: instance_name, depth)

Usage:
    py scripts/load_neptune_graph.py --dry-run
    py scripts/load_neptune_graph.py --endpoint bos-ai-neptune-prod.cluster-c254guiq2xho.us-east-1.neptune.amazonaws.com

Prerequisites:
    py -m pip install requests requests-aws4auth boto3
"""
import argparse
import json
import sys
import time

import boto3
import requests
from requests_aws4auth import AWS4Auth


def get_neptune_auth(region="us-east-1"):
    """Create SigV4 auth for Neptune IAM authentication."""
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    return AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        'neptune-db',
        session_token=credentials.token,
    )


def parse_hierarchy(filepath):
    """Parse hierarchy file into parent-child relationships."""
    records = []
    stack = []  # [(indent, instance_name, module_name)]

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


def build_cypher_queries(records, batch_size=50):
    """Build openCypher MERGE queries for Neptune bulk load."""
    queries = []

    # 1. Create all Module nodes
    modules = set()
    for r in records:
        modules.add(r["module_name"])
        if r["parent_module"]:
            modules.add(r["parent_module"])

    # Batch module creation
    module_list = sorted(modules)
    for i in range(0, len(module_list), batch_size):
        batch = module_list[i:i+batch_size]
        cypher = "UNWIND $modules AS m MERGE (n:Module {name: m})"
        queries.append({
            "query": cypher,
            "parameters": {"modules": batch}
        })

    # 2. Create INSTANTIATES edges
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        edges = []
        for r in batch:
            if r["parent_module"]:
                edges.append({
                    "parent": r["parent_module"],
                    "child": r["module_name"],
                    "instance_name": r["instance_name"],
                    "depth": r["depth"],
                })

        if edges:
            cypher = (
                "UNWIND $edges AS e "
                "MATCH (p:Module {name: e.parent}) "
                "MATCH (c:Module {name: e.child}) "
                "MERGE (p)-[r:INSTANTIATES {instance_name: e.instance_name}]->(c) "
                "SET r.depth = e.depth"
            )
            queries.append({
                "query": cypher,
                "parameters": {"edges": edges}
            })

    return queries


def execute_queries(endpoint, queries, dry_run=False):
    """Execute openCypher queries against Neptune."""
    url = f"https://{endpoint}:8182/openCypher"
    auth = get_neptune_auth()

    success = 0
    failed = 0

    for i, q in enumerate(queries):
        if dry_run:
            print(f"  [{i+1}/{len(queries)}] {q['query'][:80]}... (params: {len(q.get('parameters', {}))} keys)")
            success += 1
            continue

        try:
            resp = requests.post(url, auth=auth, json=q, timeout=60, verify=True)
            resp.raise_for_status()
            success += 1
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(queries)}] OK")
        except Exception as e:
            print(f"  [{i+1}/{len(queries)}] FAILED: {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                print(f"    Response: {e.response.text[:200]}", file=sys.stderr)
            failed += 1

    return success, failed


def main():
    parser = argparse.ArgumentParser(description="Load RTL hierarchy into Neptune Graph DB")
    parser.add_argument("--input", default="trinity_hierarchy.txt", help="Input hierarchy file")
    parser.add_argument("--endpoint", default="bos-ai-neptune-prod.cluster-c254guiq2xho.us-east-1.neptune.amazonaws.com")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    print(f"Parsing {args.input}...")
    records = parse_hierarchy(args.input)
    print(f"  {len(records)} hierarchy records parsed")

    # Count unique modules
    modules = set(r["module_name"] for r in records)
    parents = set(r["parent_module"] for r in records if r["parent_module"])
    all_modules = modules | parents
    edges = [r for r in records if r["parent_module"]]
    print(f"  {len(all_modules)} unique modules, {len(edges)} edges")

    print(f"\nBuilding openCypher queries (batch_size={args.batch_size})...")
    queries = build_cypher_queries(records, args.batch_size)
    print(f"  {len(queries)} queries generated")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Executing against Neptune: {args.endpoint}")
    start = time.time()
    success, failed = execute_queries(args.endpoint, queries, args.dry_run)
    elapsed = time.time() - start

    print(f"\nDone in {elapsed:.1f}s: {success} success, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
