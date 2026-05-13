"""
Manual Claim Injection Script for RAG v9.4

DynamoDB bos-ai-claim-db-prod 테이블에 수동 claims를 삽입한다.
v9.3 리뷰에서 식별된 factual error를 즉시 수정하기 위한 emergency overlay.

대상 Claims:
  - EDC per-column ring claim (Req 1.1, 1.3)
  - EDC port [3:0] 배열 차원 claim (Req 3.3)
  - DFX 4-wrapper chain claims (Req 4.1, 4.3)

Usage:
  py inject_manual_claims.py [--dry-run] [--table-name TABLE] [--pipeline-id ID]

Requirements validated: 1.1, 1.3, 3.3, 4.1, 4.3
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

DEFAULT_TABLE_NAME = "bos-ai-claim-db-prod"
DEFAULT_PIPELINE_ID = "tt_20260221"
DEFAULT_REGION = "ap-northeast-2"


def build_manual_claims(pipeline_id: str) -> list[dict]:
    """수동 삽입 대상 claims 목록을 생성한다.

    Returns:
        list of claim dicts ready for DynamoDB put_item
    """
    now = datetime.now(timezone.utc).isoformat()

    claims = []

    # =========================================================================
    # 1. EDC per-column ring claim (Req 1.1, 1.3)
    # =========================================================================
    claims.append({
        "claim_id": "manual_edc_ring_001",
        "claim_type": "structural",
        "claim_text": "Each column (X=0..3) has its own independent EDC ring",
        "topic": "EDC",
        "module_name": "tt_edc1_top",
        "confidence_score": Decimal("1.0"),
        "source": "manual_claim",
        "pipeline_id": pipeline_id,
        "status": "verified",
        "created_at": now,
        "updated_at": now,
    })

    # =========================================================================
    # 2. EDC port [3:0] 배열 차원 claim (Req 3.3)
    # =========================================================================
    claims.append({
        "claim_id": "manual_edc_port_array_001",
        "claim_type": "structural",
        "claim_text": (
            "EDC top-level ports use [3:0] array dimension for per-column independence: "
            "i_edc_apb_psel[3:0], o_edc_fatal_err_irq[3:0], o_edc_recov_err_irq[3:0]"
        ),
        "topic": "EDC",
        "module_name": "tt_edc1_top",
        "confidence_score": Decimal("1.0"),
        "source": "manual_claim",
        "pipeline_id": pipeline_id,
        "status": "verified",
        "created_at": now,
        "updated_at": now,
    })

    # =========================================================================
    # 3. DFX 4-wrapper chain claims (Req 4.1, 4.3)
    # =========================================================================
    dfx_modules = [
        {
            "module_name": "tt_noc_niu_router_dfx",
            "claim_id": "manual_dfx_wrapper_001",
            "description": "DFX wrapper for NOC NIU router — IJTAG scan chain element 1 of 4",
        },
        {
            "module_name": "tt_overlay_wrapper_dfx",
            "claim_id": "manual_dfx_wrapper_002",
            "description": "DFX wrapper for overlay — IJTAG scan chain element 2 of 4",
        },
        {
            "module_name": "tt_instrn_engine_wrapper_dfx",
            "claim_id": "manual_dfx_wrapper_003",
            "description": "DFX wrapper for instruction engine — IJTAG scan chain element 3 of 4",
        },
        {
            "module_name": "tt_t6_l1_partition_dfx",
            "claim_id": "manual_dfx_wrapper_004",
            "description": "DFX wrapper for T6 L1 partition — IJTAG scan chain element 4 of 4",
        },
    ]

    for dfx in dfx_modules:
        claims.append({
            "claim_id": dfx["claim_id"],
            "claim_type": "structural",
            "claim_text": (
                f"Module '{dfx['module_name']}' is a DFX wrapper in the 4-wrapper chain. "
                f"{dfx['description']}"
            ),
            "topic": "DFX",
            "module_name": dfx["module_name"],
            "confidence_score": Decimal("1.0"),
            "source": "manual_claim",
            "pipeline_id": pipeline_id,
            "status": "verified",
            "created_at": now,
            "updated_at": now,
        })

    return claims


def inject_claims(
    claims: list[dict],
    table_name: str,
    region: str,
    dry_run: bool = False,
) -> dict:
    """Claims를 DynamoDB 테이블에 삽입한다.

    Args:
        claims: 삽입할 claim 목록
        table_name: DynamoDB 테이블 이름
        region: AWS 리전
        dry_run: True이면 실제 삽입 없이 로그만 출력

    Returns:
        dict with success_count, skip_count, error_count
    """
    result = {"success_count": 0, "skip_count": 0, "error_count": 0, "errors": []}

    if dry_run:
        logger.info("[DRY-RUN] 실제 DynamoDB 쓰기를 수행하지 않습니다.")
        for claim in claims:
            logger.info(f"  [DRY-RUN] Would insert: {claim['claim_id']} — {claim['claim_text'][:60]}...")
            result["success_count"] += 1
        return result

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    for claim in claims:
        try:
            table.put_item(
                Item=claim,
                ConditionExpression="attribute_not_exists(claim_id)",
            )
            logger.info(f"  Inserted: {claim['claim_id']} (topic={claim['topic']})")
            result["success_count"] += 1
        except table.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"  Skipped (already exists): {claim['claim_id']}")
            result["skip_count"] += 1
        except Exception as e:
            logger.error(f"  Error inserting {claim['claim_id']}: {e}")
            result["error_count"] += 1
            result["errors"].append({"claim_id": claim["claim_id"], "error": str(e)})

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Inject manual claims into DynamoDB for RAG v9.4 emergency fixes"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print claims without writing to DynamoDB",
    )
    parser.add_argument(
        "--table-name",
        default=DEFAULT_TABLE_NAME,
        help=f"DynamoDB table name (default: {DEFAULT_TABLE_NAME})",
    )
    parser.add_argument(
        "--pipeline-id",
        default=DEFAULT_PIPELINE_ID,
        help=f"Pipeline ID for claims (default: {DEFAULT_PIPELINE_ID})",
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"AWS region (default: {DEFAULT_REGION})",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("RAG v9.4 Manual Claim Injection")
    logger.info(f"  Table: {args.table_name}")
    logger.info(f"  Pipeline ID: {args.pipeline_id}")
    logger.info(f"  Region: {args.region}")
    logger.info(f"  Dry Run: {args.dry_run}")
    logger.info("=" * 60)

    # Build claims
    claims = build_manual_claims(args.pipeline_id)
    logger.info(f"Total claims to inject: {len(claims)}")

    # Inject
    result = inject_claims(
        claims=claims,
        table_name=args.table_name,
        region=args.region,
        dry_run=args.dry_run,
    )

    # Summary
    logger.info("=" * 60)
    logger.info("Injection Summary:")
    logger.info(f"  Success: {result['success_count']}")
    logger.info(f"  Skipped (already exists): {result['skip_count']}")
    logger.info(f"  Errors: {result['error_count']}")
    if result["errors"]:
        for err in result["errors"]:
            logger.error(f"    {err['claim_id']}: {err['error']}")
    logger.info("=" * 60)

    # Exit code
    if result["error_count"] > 0:
        sys.exit(1)
    return 0


if __name__ == "__main__":
    main()
