# 롤백 트리거 조건 정의

## 📋 개요

본 문서는 BOS-AI VPC 통합 마이그레이션 프로젝트의 롤백 트리거 조건을 상세히 정의합니다.

---

## 🚨 자동 롤백 트리거 (즉시 실행)

### 1. 서비스 가용성 (Critical)

| 조건 | 임계값 | 측정 방법 | 롤백 Phase |
|------|--------|-----------|------------|
| 서비스 중단 시간 | 5분 이상 | CloudWatch Alarms | 해당 Phase |
| API 응답률 | 95% 미만 | CloudWatch Metrics | Phase 3-7 |
| HTTP 5xx 에러율 | 5% 초과 | ALB Metrics | Phase 5-6 |
| Lambda 실패율 | 10% 초과 | Lambda Metrics | Phase 5 |
| Knowledge Base 쿼리 실패율 | 10% 초과 | Bedrock Metrics | Phase 6 |

**측정 스크립트:**
```bash
#!/bin/bash
# 서비스 가용성 체크

# API 응답률 확인
SUCCESS_RATE=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value=app/bos-ai-alb \
  --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average \
  --query 'Datapoints[0].Average' \
  --output text)

if (( $(echo "$SUCCESS_RATE < 95" | bc -l) )); then
  echo "ALERT: API 응답률 95% 미만 - 롤백 필요"
  exit 1
fi
```

### 2. 성능 저하 (High)

| 조건 | 임계값 | 측정 방법 | 롤백 Phase |
|------|--------|-----------|------------|
| API 응답 시간 | 기준 대비 2배 초과 | CloudWatch | Phase 3-7 |
| Lambda 실행 시간 | 10초 초과 | Lambda Metrics | Phase 5 |
| Lambda 타임아웃 | 10% 초과 | Lambda Metrics | Phase 5 |
| VPC 피어링 지연시간 | 200ms 초과 | Custom Metrics | Phase 7 |
| OpenSearch 쿼리 시간 | 5초 초과 | OpenSearch Metrics | Phase 4 |
| Knowledge Base 응답 시간 | 10초 초과 | Bedrock Metrics | Phase 6 |

**측정 스크립트:**
```bash
#!/bin/bash
# 성능 체크

# Lambda 평균 실행 시간
LAMBDA_DURATION=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=document-processor \
  --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average \
  --query 'Datapoints[0].Average' \
  --output text)

if (( $(echo "$LAMBDA_DURATION > 10000" | bc -l) )); then
  echo "ALERT: Lambda 실행 시간 10초 초과 - 롤백 필요"
  exit 1
fi
```

### 3. 비용 초과 (High)

| 조건 | 임계값 | 측정 방법 | 롤백 Phase |
|------|--------|-----------|------------|
| 일일 총 비용 | 예상 대비 150% 초과 | Cost Explorer | 전체 |
| VPC 엔드포인트 비용 | $100/일 초과 | Cost Explorer | Phase 3 |
| NAT Gateway 비용 | $50/일 초과 | Cost Explorer | Phase 2 |
| OpenSearch 비용 | $200/일 초과 | Cost Explorer | Phase 4 |
| Lambda 비용 | $50/일 초과 | Cost Explorer | Phase 5 |
| Bedrock 비용 | $100/일 초과 | Cost Explorer | Phase 6 |

**측정 스크립트:**
```bash
#!/bin/bash
# 비용 체크

# 일일 비용 확인
DAILY_COST=$(aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d '1 day ago' +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
  --granularity DAILY \
  --metrics BlendedCost \
  --query 'ResultsByTime[0].Total.BlendedCost.Amount' \
  --output text)

EXPECTED_COST=100  # 예상 일일 비용 $100
THRESHOLD=$(echo "$EXPECTED_COST * 1.5" | bc)

if (( $(echo "$DAILY_COST > $THRESHOLD" | bc -l) )); then
  echo "ALERT: 일일 비용 150% 초과 ($DAILY_COST > $THRESHOLD) - 롤백 필요"
  exit 1
fi
```

### 4. 보안 이슈 (Critical)

| 조건 | 임계값 | 측정 방법 | 롤백 Phase |
|------|--------|-----------|------------|
| 비인가 접근 시도 | 10회/분 초과 | CloudTrail | 전체 |
| Security Group 규칙 위반 | 1건 이상 | Config Rules | Phase 3, 7 |
| IAM 권한 오류 | 5% 초과 | CloudTrail | Phase 5-6 |
| 데이터 유출 의심 | 1건 이상 | GuardDuty | 전체 |
| VPC Flow Logs 이상 | 비정상 트래픽 감지 | VPC Flow Logs | Phase 7 |

**측정 스크립트:**
```bash
#!/bin/bash
# 보안 체크

# 비인가 접근 시도 확인
UNAUTHORIZED_ATTEMPTS=$(aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UnauthorizedOperation \
  --start-time $(date -u -d '1 minute ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --query 'Events | length(@)' \
  --output text)

if [ "$UNAUTHORIZED_ATTEMPTS" -gt 10 ]; then
  echo "ALERT: 비인가 접근 시도 10회/분 초과 - 롤백 필요"
  exit 1
fi
```

### 5. 리소스 고갈 (High)

| 조건 | 임계값 | 측정 방법 | 롤백 Phase |
|------|--------|-----------|------------|
| Lambda 동시 실행 | 계정 한도 80% 초과 | Lambda Metrics | Phase 5 |
| VPC ENI 사용률 | 80% 초과 | VPC Metrics | Phase 3, 5 |
| OpenSearch 스토리지 | 80% 초과 | OpenSearch Metrics | Phase 4 |
| S3 버킷 용량 | 1TB 초과 | S3 Metrics | Phase 6 |

---

## ⚠️ 수동 롤백 트리거 (팀 논의 후 실행)

### 1. 운영 이슈 (Medium)

| 조건 | 설명 | 판단 기준 | 롤백 Phase |
|------|------|-----------|------------|
| 운영팀 교육 부족 | 새 시스템 운영 어려움 | 운영팀 피드백 | 전체 |
| 모니터링 도구 연동 실패 | Grafana, Datadog 등 연동 불가 | 모니터링 팀 확인 | Phase 10 |
| 문서 부족 | 운영 가이드 불충분 | 운영팀 요청 | Phase 10 |
| 알람 설정 오류 | 잘못된 알람으로 혼란 | 3회 이상 오알람 | Phase 10 |

### 2. 기술 부채 (Medium)

| 조건 | 설명 | 판단 기준 | 롤백 Phase |
|------|------|-----------|------------|
| 복잡도 증가 | 예상보다 복잡한 구조 | 아키텍트 판단 | 해당 Phase |
| 유지보수 어려움 | 코드/설정 관리 어려움 | 개발팀 피드백 | 해당 Phase |
| 기술 스택 불일치 | 기존 스택과 호환 문제 | 기술 리더 판단 | 해당 Phase |
| 의존성 문제 | 예상치 못한 의존성 발견 | 개발팀 확인 | 해당 Phase |

### 3. 비즈니스 요구사항 변경 (Low)

| 조건 | 설명 | 판단 기준 | 롤백 Phase |
|------|------|-----------|------------|
| 요구사항 변경 | 비즈니스 요구사항 변경 | 프로젝트 리더 승인 | 전체 |
| 우선순위 변경 | 다른 프로젝트 우선 | 경영진 결정 | 전체 |
| 예산 부족 | 예산 초과로 중단 | 재무팀 확인 | 전체 |

---

## 📊 모니터링 대시보드

### CloudWatch Dashboard 구성

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/Lambda", "Errors", {"stat": "Sum"}],
          [".", "Duration", {"stat": "Average"}],
          [".", "Throttles", {"stat": "Sum"}]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Lambda Metrics"
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["AWS/VPC", "BytesIn", {"stat": "Sum"}],
          [".", "BytesOut", {"stat": "Sum"}]
        ],
        "period": 300,
        "stat": "Sum",
        "region": "ap-northeast-2",
        "title": "VPC Traffic"
      }
    }
  ]
}
```

### 알람 설정

```bash
# API 응답률 알람
aws cloudwatch put-metric-alarm \
  --alarm-name bos-ai-api-response-rate-low \
  --alarm-description "API 응답률 95% 미만" \
  --metric-name TargetResponseTime \
  --namespace AWS/ApplicationELB \
  --statistic Average \
  --period 300 \
  --threshold 95 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:ap-northeast-2:533335672315:bos-ai-alerts

# Lambda 오류율 알람
aws cloudwatch put-metric-alarm \
  --alarm-name bos-ai-lambda-error-rate-high \
  --alarm-description "Lambda 오류율 10% 초과" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --dimensions Name=FunctionName,Value=document-processor \
  --alarm-actions arn:aws:sns:us-east-1:533335672315:bos-ai-alerts

# 비용 알람
aws budgets create-budget \
  --account-id 533335672315 \
  --budget file://budget-config.json \
  --notifications-with-subscribers file://budget-notifications.json
```

---

## 🔔 알림 채널

### 1. Slack 통합

```bash
# Slack Webhook 설정
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# 알림 전송 함수
send_slack_alert() {
  local message=$1
  local severity=$2
  
  curl -X POST $SLACK_WEBHOOK_URL \
    -H 'Content-Type: application/json' \
    -d "{
      \"text\": \"🚨 롤백 트리거 발생\",
      \"attachments\": [{
        \"color\": \"danger\",
        \"fields\": [
          {\"title\": \"심각도\", \"value\": \"$severity\", \"short\": true},
          {\"title\": \"메시지\", \"value\": \"$message\", \"short\": false}
        ]
      }]
    }"
}
```

### 2. SNS 토픽

```bash
# SNS 토픽 생성
aws sns create-topic \
  --name bos-ai-rollback-alerts \
  --region ap-northeast-2

# 이메일 구독
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-northeast-2:533335672315:bos-ai-rollback-alerts \
  --protocol email \
  --notification-endpoint team@example.com

# SMS 구독
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-northeast-2:533335672315:bos-ai-rollback-alerts \
  --protocol sms \
  --notification-endpoint +821012345678
```

### 3. PagerDuty 통합

```bash
# PagerDuty 이벤트 전송
send_pagerduty_alert() {
  local message=$1
  local severity=$2
  
  curl -X POST https://events.pagerduty.com/v2/enqueue \
    -H 'Content-Type: application/json' \
    -d "{
      \"routing_key\": \"YOUR_INTEGRATION_KEY\",
      \"event_action\": \"trigger\",
      \"payload\": {
        \"summary\": \"$message\",
        \"severity\": \"$severity\",
        \"source\": \"bos-ai-vpc-migration\"
      }
    }"
}
```

---

## 🤖 자동화 스크립트

### 통합 모니터링 스크립트

```bash
#!/bin/bash
# monitor-and-trigger-rollback.sh
# 모든 트리거 조건을 체크하고 필요시 롤백 실행

set -e

ROLLBACK_TRIGGERED=false
ROLLBACK_REASONS=()

# 1. 서비스 가용성 체크
check_availability() {
  echo "Checking service availability..."
  
  # API 응답률
  SUCCESS_RATE=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/ApplicationELB \
    --metric-name TargetResponseTime \
    --dimensions Name=LoadBalancer,Value=app/bos-ai-alb \
    --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 300 \
    --statistics Average \
    --query 'Datapoints[0].Average' \
    --output text)
  
  if (( $(echo "$SUCCESS_RATE < 95" | bc -l) )); then
    ROLLBACK_TRIGGERED=true
    ROLLBACK_REASONS+=("API 응답률 95% 미만: $SUCCESS_RATE%")
  fi
}

# 2. 성능 체크
check_performance() {
  echo "Checking performance..."
  
  # Lambda 실행 시간
  LAMBDA_DURATION=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Duration \
    --dimensions Name=FunctionName,Value=document-processor \
    --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 300 \
    --statistics Average \
    --query 'Datapoints[0].Average' \
    --output text)
  
  if (( $(echo "$LAMBDA_DURATION > 10000" | bc -l) )); then
    ROLLBACK_TRIGGERED=true
    ROLLBACK_REASONS+=("Lambda 실행 시간 10초 초과: ${LAMBDA_DURATION}ms")
  fi
}

# 3. 비용 체크
check_cost() {
  echo "Checking cost..."
  
  DAILY_COST=$(aws ce get-cost-and-usage \
    --time-period Start=$(date -u -d '1 day ago' +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
    --granularity DAILY \
    --metrics BlendedCost \
    --query 'ResultsByTime[0].Total.BlendedCost.Amount' \
    --output text)
  
  EXPECTED_COST=100
  THRESHOLD=$(echo "$EXPECTED_COST * 1.5" | bc)
  
  if (( $(echo "$DAILY_COST > $THRESHOLD" | bc -l) )); then
    ROLLBACK_TRIGGERED=true
    ROLLBACK_REASONS+=("일일 비용 150% 초과: \$$DAILY_COST")
  fi
}

# 4. 보안 체크
check_security() {
  echo "Checking security..."
  
  UNAUTHORIZED_ATTEMPTS=$(aws cloudtrail lookup-events \
    --lookup-attributes AttributeKey=EventName,AttributeValue=UnauthorizedOperation \
    --start-time $(date -u -d '1 minute ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --query 'Events | length(@)' \
    --output text)
  
  if [ "$UNAUTHORIZED_ATTEMPTS" -gt 10 ]; then
    ROLLBACK_TRIGGERED=true
    ROLLBACK_REASONS+=("비인가 접근 시도 10회/분 초과: $UNAUTHORIZED_ATTEMPTS회")
  fi
}

# 알림 전송
send_alert() {
  local message=$1
  
  # Slack 알림
  curl -X POST $SLACK_WEBHOOK_URL \
    -H 'Content-Type: application/json' \
    -d "{\"text\": \"🚨 롤백 트리거 발생: $message\"}"
  
  # SNS 알림
  aws sns publish \
    --topic-arn arn:aws:sns:ap-northeast-2:533335672315:bos-ai-rollback-alerts \
    --message "$message" \
    --subject "BOS-AI 롤백 트리거 발생"
}

# 롤백 실행
execute_rollback() {
  local phase=$1
  
  echo "Executing rollback for Phase $phase..."
  
  case $phase in
    3)
      cd environments/network-layer
      terraform destroy -target=module.vpc_endpoints -auto-approve
      ;;
    7)
      aws ec2 delete-vpc-peering-connection \
        --vpc-peering-connection-id pcx-06599e9d9a3fe573f \
        --region ap-northeast-2
      ;;
    *)
      echo "Manual rollback required for Phase $phase"
      ;;
  esac
}

# 메인 실행
main() {
  echo "Starting monitoring..."
  
  check_availability
  check_performance
  check_cost
  check_security
  
  if [ "$ROLLBACK_TRIGGERED" = true ]; then
    echo "❌ 롤백 트리거 발생!"
    echo "사유:"
    for reason in "${ROLLBACK_REASONS[@]}"; do
      echo "  - $reason"
    done
    
    # 알림 전송
    ALERT_MESSAGE="롤백 트리거 발생:\n$(printf '%s\n' "${ROLLBACK_REASONS[@]}")"
    send_alert "$ALERT_MESSAGE"
    
    # 롤백 실행 (자동 롤백 가능한 Phase만)
    # execute_rollback 7
    
    exit 1
  else
    echo "✅ 모든 체크 통과"
    exit 0
  fi
}

main
```

### Cron 설정

```bash
# 5분마다 모니터링 실행
*/5 * * * * /path/to/monitor-and-trigger-rollback.sh >> /var/log/rollback-monitor.log 2>&1
```

---

## 📈 트리거 이력 추적

### 로그 형식

```json
{
  "timestamp": "2026-02-22T10:30:00Z",
  "trigger_type": "automatic",
  "severity": "critical",
  "condition": "API 응답률 95% 미만",
  "value": "92%",
  "threshold": "95%",
  "phase": "Phase 7",
  "action_taken": "rollback_initiated",
  "rollback_completed": true,
  "duration_seconds": 180
}
```

### 이력 조회

```bash
# 최근 롤백 트리거 이력
aws logs filter-log-events \
  --log-group-name /aws/bos-ai/rollback-triggers \
  --start-time $(date -u -d '7 days ago' +%s)000 \
  --filter-pattern '{ $.trigger_type = "automatic" }'
```

---

**문서 버전:** 1.0  
**최종 업데이트:** 2026-02-22  
**작성자:** BOS-AI 인프라팀
