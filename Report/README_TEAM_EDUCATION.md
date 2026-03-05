# BOS-AI RAG 팀원 교육 자료 가이드

## 📋 개요

이 디렉토리에는 BOS-AI RAG 시스템을 팀원들에게 교육하기 위한 모든 자료가 포함되어 있습니다.

**작성 목적**: 
- 시스템 구축 과정을 문서화
- 팀원들이 독립적으로 배포 및 운영할 수 있도록 지원
- 새로운 팀원의 온보딩 시간 단축

---

## 🎯 팀원 교육 순서

### 1단계: 빠른 이해 (30분)

**읽을 문서**: 
- [TEAM_TRAINING_GUIDE.md](TEAM_TRAINING_GUIDE.md) - 팀원 교육 가이드

**학습 내용**:
- 시스템의 목적
- 3개 VPC의 역할
- 배포 3단계 개요
- 핵심 개념 (TGW, VPC Endpoints, Route53 Resolver, S3 복제)

### 2단계: 아키텍처 이해 (1시간)

**읽을 문서**:
- [ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md) - 아키텍처 상세 설명

**학습 내용**:
- 전체 시스템 아키텍처
- 데이터 흐름 (문서 업로드, RAG 질의, DNS 해석)
- 보안 아키텍처
- 성능 특성
- 고가용성 설계
- 확장성 고려사항

### 3단계: 배포 상세 학습 (1시간)

**읽을 문서**:
- [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md) - 배포 3단계 상세 가이드

**학습 내용**:
- 1단계: 네트워크 레이어 (VPC, TGW, VPN, DNS)
- 2단계: 앱 레이어 (Lambda, API Gateway, S3, OpenSearch, Bedrock)
- 3단계: 모니터링 레이어 (CloudWatch, CloudTrail, 알람)
- 각 단계별 구성 요소 상세
- 각 단계별 검증 항목

### 4단계: 실제 배포 (2-3시간)

**참고 문서**:
- [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md) - 배포 명령어
- [../docs/DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md) - 전체 배포 가이드

**실습 내용**:
- 네트워크 레이어 배포
- 앱 레이어 배포
- 모니터링 레이어 배포
- 배포 후 검증

### 5단계: 테스트 및 검증 (1시간)

**참고 문서**:
- [20260303_VPN_CONNECTIVITY_TEST_RESULTS.md](20260303_VPN_CONNECTIVITY_TEST_RESULTS.md) - VPN 테스트 결과
- [20260303_DNS_LOOKUP_TEST_RESULTS.md](20260303_DNS_LOOKUP_TEST_RESULTS.md) - DNS 테스트 결과

**테스트 항목**:
- VPN 연결성 테스트
- DNS 해석 테스트
- API 엔드포인트 테스트
- 문서 업로드 테스트
- RAG 질의 테스트

### 6단계: 운영 및 모니터링 (30분)

**참고 문서**:
- [../docs/OPERATIONAL_RUNBOOK.md](../docs/OPERATIONAL_RUNBOOK.md) - 운영 가이드

**학습 내용**:
- CloudWatch 모니터링
- 알람 설정
- 로그 조회
- 트러블슈팅

---

## 📚 주요 문서 설명

### 필수 문서 (반드시 읽어야 함)

| 문서 | 설명 | 읽는 시간 |
|------|------|---------|
| [TEAM_TRAINING_GUIDE.md](TEAM_TRAINING_GUIDE.md) | 팀원 교육 가이드 - 시작점 | 30분 |
| [ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md) | 아키텍처 상세 설명 | 1시간 |
| [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md) | 배포 3단계 상세 가이드 | 1시간 |

### 참고 문서 (필요시 읽음)

| 문서 | 설명 | 읽는 시간 |
|------|------|---------|
| [../docs/DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md) | 전체 배포 가이드 | 1시간 |
| [../docs/OPERATIONAL_RUNBOOK.md](../docs/OPERATIONAL_RUNBOOK.md) | 운영 및 트러블슈팅 | 1시간 |
| [20260303_VPN_CONNECTIVITY_TEST_RESULTS.md](20260303_VPN_CONNECTIVITY_TEST_RESULTS.md) | VPN 테스트 결과 | 30분 |
| [20260303_DNS_LOOKUP_TEST_RESULTS.md](20260303_DNS_LOOKUP_TEST_RESULTS.md) | DNS 테스트 결과 | 30분 |
| [20260303_FORTIGATE_TGW_VPN_SETUP_GUIDE.md](20260303_FORTIGATE_TGW_VPN_SETUP_GUIDE.md) | FortiGate VPN 설정 | 1시간 |

### 참고용 문서 (배포 후 참고)

| 문서 | 설명 |
|------|------|
| [20260303_AWS_RESOURCES_INVENTORY.md](20260303_AWS_RESOURCES_INVENTORY.md) | AWS 리소스 인벤토리 |
| [20260303_DEPLOYMENT_SUMMARY.md](20260303_DEPLOYMENT_SUMMARY.md) | 배포 요약 |
| [20260303_ACTUAL_DEPLOYED_RESOURCES.md](20260303_ACTUAL_DEPLOYED_RESOURCES.md) | 실제 배포된 리소스 |

---

## 🎓 학습 경로별 가이드

### 경로 1: 빠른 배포 (4시간)

**대상**: 경험 많은 DevOps 엔지니어

1. [TEAM_TRAINING_GUIDE.md](TEAM_TRAINING_GUIDE.md) - 30분
2. [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md) - 30분
3. 실제 배포 - 2시간
4. 테스트 - 1시간

### 경로 2: 완전한 이해 (6시간)

**대상**: 새로운 팀원 또는 시스템 관리자

1. [TEAM_TRAINING_GUIDE.md](TEAM_TRAINING_GUIDE.md) - 30분
2. [ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md) - 1시간
3. [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md) - 1시간
4. 실제 배포 - 2시간
5. 테스트 및 검증 - 1시간 30분

### 경로 3: 심화 학습 (8시간)

**대상**: 시스템 설계자 또는 아키텍트

1. [TEAM_TRAINING_GUIDE.md](TEAM_TRAINING_GUIDE.md) - 30분
2. [ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md) - 1시간 30분
3. [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md) - 1시간
4. [../docs/DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md) - 1시간
5. [../docs/OPERATIONAL_RUNBOOK.md](../docs/OPERATIONAL_RUNBOOK.md) - 1시간
6. 실제 배포 - 2시간

---

## 🔍 문서 선택 가이드

### "시스템이 뭐하는 거예요?"
→ [TEAM_TRAINING_GUIDE.md](TEAM_TRAINING_GUIDE.md)의 "시스템 아키텍처 한눈에 보기" 섹션

### "어떻게 배포하나요?"
→ [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md)의 "배포 명령어" 섹션

### "각 단계에서 뭘 배포하나요?"
→ [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md)의 "구성 요소" 섹션

### "데이터가 어떻게 흐르나요?"
→ [ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md)의 "데이터 흐름" 섹션

### "배포 후 뭘 확인해야 하나요?"
→ [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md)의 "검증 항목" 섹션

### "문제가 생겼어요"
→ [../docs/OPERATIONAL_RUNBOOK.md](../docs/OPERATIONAL_RUNBOOK.md)의 "트러블슈팅" 섹션

### "VPN 설정이 궁금해요"
→ [20260303_FORTIGATE_TGW_VPN_SETUP_GUIDE.md](20260303_FORTIGATE_TGW_VPN_SETUP_GUIDE.md)

### "테스트 결과가 궁금해요"
→ [20260303_VPN_CONNECTIVITY_TEST_RESULTS.md](20260303_VPN_CONNECTIVITY_TEST_RESULTS.md)
→ [20260303_DNS_LOOKUP_TEST_RESULTS.md](20260303_DNS_LOOKUP_TEST_RESULTS.md)

---

## 📊 시스템 구성 요약

### 3개 VPC

| VPC | CIDR | 용도 | 리전 |
|-----|------|------|------|
| Private RAG VPC | 10.10.0.0/16 | 프론트엔드 (Lambda, API) | Seoul |
| US Backend VPC | 10.20.0.0/16 | 백엔드 (Bedrock, OpenSearch) | Virginia |
| Logging VPC | 10.200.0.0/16 | 모니터링 (CloudWatch, CloudTrail) | Seoul |

### 배포 3단계

| 단계 | 구성 요소 | 위치 |
|------|---------|------|
| 1. 네트워크 | VPC, TGW, VPN, DNS, VPC Endpoints | `environments/network-layer/` |
| 2. 앱 | Lambda, API Gateway, S3, OpenSearch, Bedrock | `environments/app-layer/bedrock-rag/` |
| 3. 모니터링 | CloudWatch, CloudTrail, 알람 | `environments/monitoring/` |

### 주요 리소스

| 리소스 | ID | 용도 |
|--------|-----|------|
| Transit Gateway | tgw-0897383168475b532 | VPC 간 라우팅 |
| VPC Peering | pcx-0a44f0b90565313f7 | Seoul ↔ Virginia |
| Route53 Resolver | rslvr-in-93384eeb51fc4c4db | DNS 해석 |
| API Gateway | r0qa9lzhgi | RAG API 엔드포인트 |
| Lambda | lambda-document-processor-seoul-prod | 문서 처리 |
| OpenSearch | bos-ai-vectors | 벡터 저장소 |
| Bedrock KB | FNNOP3VBZV | 지식 기반 |

---

## ✅ 배포 체크리스트

### 배포 전
- [ ] AWS 자격증명 설정
- [ ] Terraform 설치 (>= 1.0)
- [ ] 변수 파일 준비

### 1단계 배포
- [ ] 네트워크 레이어 terraform apply
- [ ] VPC 생성 확인
- [ ] TGW 라우팅 확인
- [ ] VPC Endpoints 생성 확인

### 2단계 배포
- [ ] Lambda 배포 패키지 준비
- [ ] 앱 레이어 terraform apply
- [ ] API Gateway 배포 확인
- [ ] S3 크로스 리전 복제 확인
- [ ] Bedrock KB 생성 확인

### 3단계 배포
- [ ] 모니터링 레이어 terraform apply
- [ ] CloudWatch 로그 수집 확인
- [ ] 알람 설정 확인

### 배포 후
- [ ] VPN 연결성 테스트
- [ ] DNS 해석 테스트
- [ ] API 엔드포인트 테스트
- [ ] 문서 업로드 테스트
- [ ] RAG 질의 테스트

---

## 🎓 학습 완료 기준

### 이론 학습 완료
- [ ] 시스템 목적 설명 가능
- [ ] 3개 VPC의 역할 설명 가능
- [ ] 배포 3단계 설명 가능
- [ ] 데이터 흐름 설명 가능
- [ ] 보안 정책 설명 가능

### 실습 완료
- [ ] 배포 3단계 모두 완료
- [ ] 모든 테스트 통과
- [ ] CloudWatch 대시보드 확인 가능
- [ ] 로그 조회 가능

### 운영 준비 완료
- [ ] 알람 설정 확인
- [ ] 트러블슈팅 방법 숙지
- [ ] 긴급 연락처 확인

---

## 📞 질문 및 지원

**질문이 있으신가요?**

1. 먼저 해당 문서의 FAQ 또는 트러블슈팅 섹션 확인
2. 팀 Slack 채널에 질문
3. 담당자에게 직접 연락

**추천 질문 순서**:
1. "이게 뭐하는 거예요?" → [TEAM_TRAINING_GUIDE.md](TEAM_TRAINING_GUIDE.md)
2. "어떻게 배포하나요?" → [DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md)
3. "왜 이렇게 설계했나요?" → [ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md)
4. "문제가 생겼어요" → [../docs/OPERATIONAL_RUNBOOK.md](../docs/OPERATIONAL_RUNBOOK.md)

---

## 📈 다음 단계

배포 완료 후:

1. **성능 최적화** - Lambda 함수 최적화, 캐싱 추가
2. **비용 최적화** - 리소스 크기 조정, 라이프사이클 정책
3. **재해 복구** - 백업 및 복구 계획 수립
4. **자동화** - CI/CD 파이프라인 구축

---

**작성일**: 2026-03-06  
**버전**: 1.0  
**대상**: 팀원 교육용
