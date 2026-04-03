# BOS-AI 문서 디렉토리

> 스펙(`.kiro/specs/`)과 연계된 문서 구조

## 디렉토리 구조

```
docs/
├── 1_bedrock-rag-deployment/     # Spec 1: AWS Bedrock RAG 배포
├── 2_vpc-consolidation/          # Spec 2: VPC 통합 마이그레이션
├── 3_private-rag-api/            # Spec 3: Private RAG API
├── 4_multi-file-upload/          # Spec 4: 다중 파일 업로드
├── 5_rag-search-optimization/    # Spec 5: RAG 검색 최적화
├── 7_enterprise-rbac-pipeline/   # Spec 7: Enterprise RBAC 파이프라인
├── 8_quicksight-private-integration/  # QuickSight Private 통합
└── common/                       # 공통 (네이밍, 태깅, 연락처)
```

## 스펙 - 문서 매핑

| Spec | 스펙 경로 | 문서 폴더 | 주요 문서 |
|------|----------|----------|----------|
| 1 | `.kiro/specs/1_aws-bedrock-rag-deployment/` | `docs/1_bedrock-rag-deployment/` | DEPLOYMENT_GUIDE, TESTING_GUIDE, rollback-plan |
| 2 | `.kiro/specs/2_bos-ai-vpc-consolidation/` | `docs/2_vpc-consolidation/` | architecture-as-is-to-be, vpn-migration-report, tgw-migration-guide |
| 3 | `.kiro/specs/3_private-rag-api/` | `docs/3_private-rag-api/` | deep-dive-*, dns-conditional-forwarding, OPERATIONAL_RUNBOOK |
| 4 | `.kiro/specs/4_multi-file-upload/` | `docs/4_multi-file-upload/` | (rag-upload-guide 참조) |
| 5 | `.kiro/specs/5_rag-search-optimization/` | `docs/5_rag-search-optimization/` | (구현 중) |
| 7 | `.kiro/specs/7_enterprise-rbac-pipeline/` | `docs/7_enterprise-rbac-pipeline/` | (구현 예정) |
| QS | `.kiro/specs/quicksight-private-integration/` | `docs/8_quicksight-private-integration/` | quicksight-guide, quick-suite-adoption-plan |
| - | - | `docs/common/` | naming-conventions, tagging-strategy, emergency-contacts |

## 상위 문서

| 문서 | 위치 | 설명 |
|------|------|------|
| 시스템 개요 | `BOS-AI-Private-RAG-System-Overview.md` (루트) | 팀 교육용 전체 아키텍처 문서 |

## 최종 업데이트: 2026-04-03
