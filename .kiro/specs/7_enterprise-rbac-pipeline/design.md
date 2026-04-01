# 설계 문서: Enterprise RBAC 자동 프로비저닝 플랫폼

## 개요 (Overview)

본 설계 문서는 BOS Semi의 Enterprise RBAC 자동 프로비저닝 플랫폼의 기술 아키텍처를 정의한다. 이 시스템은 AWS IAM Identity Center를 전사 ID/접근 관리의 중앙 Source of Truth로 활용하여, 내부 승인 워크플로우(Jira/포털)에서 발생한 RBAC 변경 요청을 웹훅으로 수신하고, IAM Identity Center 그룹 멤버십을 자동으로 관리한다. 두 가지 통합 패턴을 지원한다: Pattern A (SaaS — SAML SSO + SCIM 자동 프로비저닝)와 Pattern B (사내 서비스 — OIDC + Group Claims JIT 프로비저닝).

초기 롤아웃은 LLM 서비스(ChatGPT Team, AWS Q)를 대상으로 하며, 향후 Jira, Confluence, 사내 Django 서비스 등으로 확장 시 GROUP_MAP 추가만으로 대응할 수 있도록 무제한 서비스 확장성을 Day 1부터 아키텍처에 내재한다.

핵심 설계 원칙:
- 폭발 반경 격리: 기존 에어갭 RAG 인프라(10.10.0.0/16)와 완전히 분리된 DMZ VPC(10.30.0.0/16)에서 실행
- 멱등성: 모든 프로비저닝 작업은 중복 실행에 안전하도록 설계
- 비용 효율: 추가 인프라 비용 월 $100 이내 (NAT GW 1개, VPC Endpoint 3개, WAF 단일 규칙, SQS 표준 큐)
- 기존 IaC 패턴 준수: 프로젝트의 Terraform 레이어 구조, 모듈 패턴, 태깅 전략을 그대로 따름
- 무제한 확장성: GROUP_MAP 딕셔너리 확장만으로 새 서비스 온보딩 가능