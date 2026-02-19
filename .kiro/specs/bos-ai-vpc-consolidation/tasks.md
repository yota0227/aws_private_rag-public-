# BOS-AI VPC 통합 마이그레이션 구현 작업

## Phase 1: 준비 및 사전 작업

- [x] 1. 현재 상태 백업 및 문서화
  - [x] 1.1 Terraform state 파일 백업
  - [x] 1.2 현재 VPC 설정 문서화 (CIDR, 서브넷, 라우팅)
  - [x] 1.3 현재 Security Group 규칙 문서화
  - [x] 1.4 현재 IAM Role 및 정책 문서화

- [x] 2. 네이밍 규칙 확정 및 변수 파일 준비
  - [x] 2.1 네이밍 규칙 문서 작성
  - [x] 2.2 Terraform 변수 파일 업데이트 (environments/seoul/terraform.tfvars)
  - [x] 2.3 태그 전략 문서 작성

- [ ] 3. 롤백 계획 수립
  - [~] 3.1 각 Phase별 롤백 절차 문서화
  - [~] 3.2 롤백 트리거 조건 정의
  - [~] 3.3 긴급 연락망 구성

## Phase 2: VPC 네이밍 변경

- [x] 4. VPC 리소스 태그 업데이트
  - [x] 4.1 VPC 태그 변경 (vpc-bos-ai-seoul-prod-01)
  - [x] 4.2 서브넷 태그 변경 (sn-private/public-bos-ai-seoul-prod-01a/c)
  - [x] 4.3 Route Table 태그 변경
  - [x] 4.4 NAT Gateway 태그 변경
  - [x] 4.5 Internet Gateway 태그 변경

- [ ] 5. Security Group 이름 및 태그 업데이트
  - [~] 5.1 기존 Security Group 이름 변경 (Terraform)
  - [~] 5.2 Security Group 태그 업데이트
  - [~] 5.3 Security Group 설명 업데이트

- [ ] 6. Route53 Resolver 엔드포인트 이름 변경
  - [~] 6.1 Inbound Endpoint 이름 변경 (ibe-bos-ai-seoul-prod)
  - [~] 6.2 Outbound Endpoint 이름 변경 (obe-bos-ai-seoul-prod)

- [ ] 7. 네이밍 변경 검증
  - [~] 7.1 모든 리소스 이름 확인
  - [~] 7.2 태그 일관성 확인
  - [~] 7.3 기존 기능 정상 동작 확인

## Phase 3: VPC 엔드포인트 구성

- [x] 8. Security Group 생성 (VPC 엔드포인트용)
  - [x] 8.1 sg-vpc-endpoints-bos-ai-seoul-prod 생성
  - [x] 8.2 Inbound 규칙 추가 (443 from 10.200.0.0/16, 192.128.0.0/16)
  - [x] 8.3 Outbound 규칙 추가 (all to 0.0.0.0/0)

- [x] 9. Interface Endpoints 생성
  - [x] 9.1 Bedrock Runtime 엔드포인트 생성
  - [x] 9.2 Secrets Manager 엔드포인트 생성
  - [x] 9.3 CloudWatch Logs 엔드포인트 생성
  - [x] 9.4 Private DNS 활성화 확인

- [x] 10. Gateway Endpoint 생성
  - [x] 10.1 S3 Gateway 엔드포인트 생성
  - [x] 10.2 Route Table 연결 확인

- [ ] 11. VPC 엔드포인트 연결 테스트
  - [~] 11.1 Bedrock Runtime 엔드포인트 테스트 (nslookup, curl)
  - [~] 11.2 Secrets Manager 엔드포인트 테스트
  - [~] 11.3 S3 Gateway 엔드포인트 테스트

## Phase 4: OpenSearch Serverless 배포

- [x] 12. Security Group 생성 (OpenSearch용)
  - [x] 12.1 sg-opensearch-bos-ai-seoul-prod 생성
  - [x] 12.2 Inbound 규칙 추가 (443 from Lambda, Bedrock, 온프레미스, 버지니아)
  - [x] 12.3 Outbound 규칙 추가

- [x] 13. OpenSearch Serverless 컬렉션 생성
  - [x] 13.1 컬렉션 생성 (bos-ai-rag-vectors-prod, Vectorsearch)
  - [x] 13.2 Standby Replicas 활성화
  - [x] 13.3 암호화 설정 (AWS managed key)

- [x] 14. OpenSearch VPC 엔드포인트 생성
  - [x] 14.1 VPC 엔드포인트 생성 (vpce-opensearch-serverless-seoul-prod)
  - [x] 14.2 서브넷 연결 (2a, 2c)
  - [x] 14.3 Security Group 연결

- [x] 15. OpenSearch 액세스 정책 설정
  - [x] 15.1 Data Access Policy 생성 (Lambda, Bedrock Role 허용)
  - [x] 15.2 Network Policy 생성 (VPC 엔드포인트만 허용)
  - [x] 15.3 Encryption Policy 생성

- [x] 16. OpenSearch 인덱스 생성
  - [x] 16.1 인덱스 매핑 파일 준비 (opensearch_index_mapping.json)
  - [x] 16.2 인덱스 생성 스크립트 실행
  - [x] 16.3 인덱스 설정 확인

- [ ] 17. OpenSearch 연결 테스트
  - [~] 17.1 VPC 내부에서 연결 테스트
  - [~] 17.2 온프레미스에서 연결 테스트 (VPN 통해)
  - [~] 17.3 샘플 데이터 인덱싱 테스트

## Phase 5: Lambda 배포

- [ ] 18. Security Group 생성 (Lambda용)
  - [x] 18.1 sg-lambda-bos-ai-seoul-prod 생성
  - [~] 18.2 Outbound 규칙 추가 (443 to OpenSearch, VPC Endpoints, 버지니아)

- [ ] 19. IAM Role 생성 (Lambda용)
  - [~] 19.1 role-lambda-document-processor-seoul-prod 생성
  - [~] 19.2 S3 권한 추가 (GetObject, PutObject)
  - [~] 19.3 OpenSearch 권한 추가 (ESHttpPost, ESHttpPut)
  - [~] 19.4 Bedrock 권한 추가 (InvokeModel)
  - [~] 19.5 Secrets Manager 권한 추가 (GetSecretValue)
  - [~] 19.6 CloudWatch Logs 권한 추가
  - [~] 19.7 VPC 권한 추가 (ENI 관리)

- [ ] 20. Lambda 함수 배포
  - [~] 20.1 Lambda 함수 코드 패키징 (lambda/document-processor/)
  - [~] 20.2 Lambda 함수 생성 (lambda-document-processor-seoul-prod)
  - [~] 20.3 VPC 설정 (서브넷, Security Group)
  - [~] 20.4 환경 변수 설정
  - [~] 20.5 메모리 및 타임아웃 설정

- [ ] 21. Lambda 트리거 설정
  - [~] 21.1 S3 Event 트리거 설정 (버지니아 버킷)
  - [~] 21.2 EventBridge 스케줄 설정 (선택사항)

- [ ] 22. Lambda 테스트
  - [~] 22.1 테스트 이벤트 생성
  - [~] 22.2 함수 실행 테스트
  - [~] 22.3 OpenSearch 인덱싱 확인
  - [~] 22.4 CloudWatch Logs 확인

## Phase 6: Bedrock Knowledge Base 설정

- [ ] 23. Security Group 생성 (Bedrock KB용)
  - [x] 23.1 sg-bedrock-kb-bos-ai-seoul-prod 생성
  - [~] 23.2 Outbound 규칙 추가 (443 to OpenSearch, VPC Endpoints)

- [ ] 24. IAM Role 생성 (Bedrock KB용)
  - [~] 24.1 role-bedrock-kb-seoul-prod 생성
  - [x] 24.2 S3 권한 추가 (GetObject, ListBucket)
  - [x] 24.3 OpenSearch Serverless 권한 추가 (APIAccessAll)
  - [x] 24.4 Bedrock 권한 추가 (InvokeModel)

- [ ] 25. Bedrock Knowledge Base 생성
  - [ ] 25.1 Knowledge Base 생성 (bos-ai-kb-seoul-prod)
  - [ ] 25.2 Foundation Model 설정 (amazon.titan-embed-text-v1)
  - [ ] 25.3 Vector Store 연결 (OpenSearch Serverless)
  - [ ] 25.4 VPC 설정 (서브넷, Security Group)

- [ ] 26. 데이터 소스 연결
  - [ ] 26.1 S3 데이터 소스 추가 (버지니아 버킷)
  - [ ] 26.2 S3 데이터 소스 추가 (서울 버킷, 선택사항)
  - [ ] 26.3 동기화 설정

- [ ] 27. Knowledge Base 동기화 및 테스트
  - [ ] 27.1 초기 동기화 실행
  - [ ] 27.2 동기화 상태 확인
  - [ ] 27.3 샘플 쿼리 테스트
  - [ ] 27.4 검색 결과 확인

## Phase 7: VPC 피어링 구성

- [x] 28. VPC Peering Connection 생성
  - [x] 28.1 Peering Connection 생성 (서울 → 버지니아)
  - [x] 28.2 Peering Connection 수락 (버지니아)
  - [x] 28.3 DNS Resolution 활성화 (양방향)

- [x] 29. 라우팅 테이블 업데이트 (서울)
  - [x] 29.1 Private Route Table에 버지니아 경로 추가 (10.20.0.0/16 → pcx-xxxxx)
  - [x] 29.2 라우팅 우선순위 확인

- [x] 30. 라우팅 테이블 업데이트 (버지니아)
  - [x] 30.1 Private Route Table에 서울 경로 추가 (10.200.0.0/16 → pcx-xxxxx)
  - [x] 30.2 라우팅 우선순위 확인

- [ ] 31. Security Group 규칙 추가
  - [ ] 31.1 서울 Lambda SG에 버지니아 CIDR 허용
  - [ ] 31.2 서울 OpenSearch SG에 버지니아 CIDR 허용
  - [ ] 31.3 버지니아 S3 VPC Endpoint SG에 서울 CIDR 허용

- [ ] 32. VPC 피어링 연결 테스트
  - [ ] 32.1 서울 → 버지니아 ping 테스트
  - [ ] 32.2 서울 Lambda → 버지니아 S3 접근 테스트
  - [ ] 32.3 지연시간 측정 (<200ms 확인)

## Phase 8: 통합 테스트

- [ ] 33. 전체 파이프라인 테스트
  - [ ] 33.1 버지니아 S3에 테스트 문서 업로드
  - [ ] 33.2 Lambda 자동 트리거 확인
  - [ ] 33.3 Bedrock 임베딩 생성 확인
  - [ ] 33.4 OpenSearch 인덱싱 확인
  - [ ] 33.5 Knowledge Base 쿼리 테스트

- [ ] 34. 온프레미스 연결 테스트
  - [ ] 34.1 온프레미스 → 서울 VPC ping 테스트
  - [ ] 34.2 온프레미스 → OpenSearch Serverless 접근 테스트
  - [ ] 34.3 온프레미스 → Bedrock KB 쿼리 테스트

- [ ] 35. 기존 로깅 인프라 검증
  - [ ] 35.1 EC2 로그 수집기 정상 동작 확인
  - [ ] 35.2 Firehose 전송 정상 동작 확인
  - [ ] 35.3 OpenSearch Managed 인덱싱 확인
  - [ ] 35.4 Grafana 대시보드 정상 표시 확인

- [ ] 36. 성능 테스트
  - [ ] 36.1 지연시간 측정 (온프레미스 → 서울, 서울 → 버지니아)
  - [ ] 36.2 Lambda 실행 시간 측정
  - [ ] 36.3 문서 처리 속도 측정
  - [ ] 36.4 동시 실행 테스트

- [ ] 37. 보안 테스트
  - [ ] 37.1 Security Group 규칙 검증 (nmap)
  - [ ] 37.2 IAM Role 권한 검증
  - [ ] 37.3 VPC 엔드포인트 접근 검증
  - [ ] 37.4 tfsec 스캔 실행
  - [ ] 37.5 checkov 스캔 실행

## Phase 9: 기존 VPC 제거

- [ ] 38. 마이그레이션 완료 확인
  - [ ] 38.1 모든 리소스가 서울 통합 VPC로 이동 확인
  - [ ] 38.2 기존 BOS-AI-RAG VPC에 남은 리소스 확인
  - [ ] 38.3 24시간 안정성 모니터링

- [ ] 39. 기존 VPC 피어링 삭제
  - [ ] 39.1 기존 피어링 연결 삭제 (BOS-AI-RAG VPC ↔ 버지니아)
  - [ ] 39.2 라우팅 테이블 정리

- [ ] 40. VPN Gateway 분리
  - [ ] 40.1 BOS-AI-RAG VPC의 VPN Gateway 분리
  - [ ] 40.2 VPN Gateway 삭제 (vgw-0461cd4d6a4463f67)

- [ ] 41. BOS-AI-RAG VPC 삭제
  - [ ] 41.1 서브넷 삭제
  - [ ] 41.2 Security Group 삭제
  - [ ] 41.3 Route Table 삭제
  - [ ] 41.4 VPC 삭제 (vpc-0f759f00e5df658d1)

- [ ] 42. Terraform State 정리
  - [ ] 42.1 삭제된 리소스 state 제거
  - [ ] 42.2 State 파일 백업
  - [ ] 42.3 State 일관성 확인

## Phase 10: 모니터링 및 문서화

- [ ] 43. CloudWatch 모니터링 설정
  - [ ] 43.1 VPC Flow Logs 활성화
  - [ ] 43.2 Lambda 메트릭 수집 설정
  - [ ] 43.3 OpenSearch 메트릭 수집 설정
  - [ ] 43.4 CloudWatch Dashboard 생성

- [ ] 44. CloudWatch Alarms 설정
  - [ ] 44.1 VPN 연결 상태 알람
  - [ ] 44.2 NAT Gateway 오류 알람
  - [ ] 44.3 Lambda 오류율 알람
  - [ ] 44.4 OpenSearch 클러스터 상태 알람
  - [ ] 44.5 비용 알람

- [ ] 45. 문서 업데이트
  - [ ] 45.1 아키텍처 다이어그램 업데이트
  - [ ] 45.2 네트워크 다이어그램 생성
  - [ ] 45.3 운영 가이드 작성
  - [ ] 45.4 장애 대응 가이드 작성
  - [ ] 45.5 README.md 업데이트

- [ ] 46. 지식 이전
  - [ ] 46.1 운영팀 교육 자료 준비
  - [ ] 46.2 운영팀 교육 실시
  - [ ] 46.3 Q&A 세션

## Property-Based Testing Tasks

- [ ] 47. 네트워크 연결성 속성 테스트
  - [ ] 47.1 Property 1.1: VPN 라우팅 일관성 테스트
  - [ ] 47.2 Property 1.2: VPC 피어링 양방향 라우팅 테스트

- [ ] 48. 보안 속성 테스트
  - [ ] 48.1 Property 2.1: Security Group 최소 권한 테스트
  - [ ] 48.2 Property 2.2: VPC 엔드포인트 Private DNS 테스트

- [ ] 49. 고가용성 속성 테스트
  - [ ] 49.1 Property 3.1: Multi-AZ 배포 테스트
  - [ ] 49.2 Property 3.2: VPC 엔드포인트 이중화 테스트

- [ ] 50. 데이터 무결성 속성 테스트
  - [ ] 50.1 Property 4.1: 기존 로깅 파이프라인 보존 테스트
  - [ ] 50.2 Property 4.2: OpenSearch 인덱스 매핑 일관성 테스트

- [ ] 51. 네이밍 일관성 속성 테스트
  - [ ] 51.1 Property 5.1: 리소스 네이밍 규칙 테스트
  - [ ] 51.2 Property 5.2: 태그 일관성 테스트

- [ ] 52. IAM 권한 속성 테스트
  - [ ] 52.1 Property 6.1: Lambda 최소 권한 테스트
  - [ ] 52.2 Property 6.2: 교차 계정 접근 금지 테스트

- [ ] 53. 성능 속성 테스트
  - [ ] 53.1 Property 7.1: VPC 피어링 지연시간 테스트
  - [ ] 53.2 Property 7.2: Lambda 실행 시간 테스트

## 최종 검증

- [ ] 54. 전체 시스템 검증
  - [ ] 54.1 모든 요구사항 충족 확인
  - [ ] 54.2 모든 정확성 속성 통과 확인
  - [ ] 54.3 성능 기준 충족 확인
  - [ ] 54.4 보안 기준 충족 확인
  - [ ] 54.5 비용 기준 충족 확인

- [ ] 55. 프로덕션 전환
  - [ ] 55.1 최종 승인 획득
  - [ ] 55.2 프로덕션 전환 공지
  - [ ] 55.3 모니터링 강화 (첫 주)
  - [ ] 55.4 사후 검토 회의

## 참고사항

### 작업 우선순위
- Phase 1-2: 준비 및 네이밍 (중단 없음)
- Phase 3-7: 신규 리소스 배포 (기존 인프라 영향 없음)
- Phase 8: 통합 테스트 (검증)
- Phase 9: 기존 VPC 제거 (최종 정리)
- Phase 10: 모니터링 및 문서화

### 롤백 포인트
- Phase 2 완료 후: 태그만 변경, 쉬운 롤백
- Phase 7 완료 후: 신규 리소스 삭제로 롤백
- Phase 9 시작 전: 마지막 롤백 가능 시점

### 예상 소요 시간
- Phase 1-2: 1주
- Phase 3-7: 2주
- Phase 8: 1주
- Phase 9-10: 1주
- 총 5주 예상
