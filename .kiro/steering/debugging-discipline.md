---
inclusion: auto
description: "디버깅 규율 — 조사·가설·검증을 통한 체계적 문제 해결 및 AWS 네트워크 점검 체크리스트"
---

# 디버깅 규율

## 문제 해결 절차 (필수)

1. **조사 먼저, 결론 나중** — 추측으로 결론 내지 마. 데이터로 확인해.
2. **가능한 원인 목록 나열** — 문제 발생 시 가능한 원인을 모두 리스트업하고, 하나씩 순서대로 검증.
3. **한 번에 하나만 변경** — 여러 개를 동시에 바꾸면 뭐가 원인인지 모름.
4. **수정 전에 의존 관계 확인** — SG(Ingress + Egress), Route Table, VPC Endpoint, IAM, DNS 전체를 사전 점검.
5. **영향 범위 분석** — 이 변경이 다른 서비스에 영향을 주는지 반드시 확인.

## 금지 행동

- "Understood"만 답하고 행동 안 하기
- 확인 없이 "아키텍처 문제"라고 단정짓기
- 사용자에게 이것저것 시도해보라고 던지기 (내가 계획을 세워서 진행해야 함)
- 동일한 에러에 같은 접근을 반복하기

## AWS 네트워크 디버깅 체크리스트

문제: A → B 연결 안 됨

1. A의 SG **Egress** — 목적지 포트/CIDR 허용?
2. B의 SG **Ingress** — 소스 포트/CIDR 허용?
3. A의 Route Table — B의 CIDR로 가는 경로 존재?
4. B의 Route Table — A의 CIDR로 응답이 돌아오는 경로 존재?
5. VPC Peering/TGW — 상태 Active? 양쪽 Route Table에 등록?
6. VPC Endpoint — 해당 서비스의 Endpoint가 같은 VPC/서브넷에 존재?
7. IAM — 호출 주체에 필요한 권한이 있는지?
8. DNS — 이름이 올바른 IP로 리졸브되는지?

## 비용 관련

- Lambda 비동기 호출(`InvocationType=Event`) 성공은 "AWS가 큐에 넣었다"는 것만 의미. 실제 처리 결과는 별도 확인 필요.
- Bedrock API 쓰로틀링 시 Lambda가 300초 풀 타임아웃으로 비용 폭발 가능 → `maximum_retry_attempts = 0` + DLQ 필수.
