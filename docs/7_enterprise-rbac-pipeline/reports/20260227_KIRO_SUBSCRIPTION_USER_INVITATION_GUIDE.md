# Kiro 구독 사용자 초대 가이드

작성일: 2026-02-27

## 개요

Kiro IDE의 내장 구독 관리 기능을 통해 사용자를 초대하고 구독을 관리하는 방법을 설명합니다.

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    Kiro IDE (Client)                     │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Subscription Management UI                      │   │
│  │  ├─ User Invitation Panel                        │   │
│  │  ├─ Subscription Status                          │   │
│  │  ├─ Team Management                              │   │
│  │  └─ Billing Information                          │   │
│  └──────────────────────────────────────────────────┘   │
│           │                                              │
│           └─ Kiro Backend API                           │
│              ├─ Authentication (OAuth/API Key)          │
│              ├─ User Management                         │
│              ├─ Subscription Management                 │
│              └─ Invitation Processing                   │
│                                                           │
└─────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                    AWS Infrastructure                    │
│                   (us-east-1 / Virginia)                 │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  S3: bos-ai-kiro-logs                            │   │
│  │  └─ User Prompts & Metadata                      │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Secrets Manager                                 │   │
│  │  ├─ API Keys                                     │   │
│  │  ├─ Database Credentials                         │   │
│  │  └─ S3 Configuration                             │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Lambda Functions                                │   │
│  │  ├─ Prompt Processor                             │   │
│  │  └─ Metadata Analyzer                            │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  EventBridge                                     │   │
│  │  ├─ Prompt Received Events                       │   │
│  │  ├─ Prompt Error Events                          │   │
│  │  └─ All Events Logging                           │   │
│  └──────────────────────────────────────────────────┘   │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Kiro IDE 구독 관리 기능

### 1. 구독 관리 패널 접근

#### 방법 1: 메뉴를 통한 접근
```
Kiro IDE 메인 메뉴
├─ View (보기)
│  └─ Subscription Management (구독 관리)
│     └─ Open Subscription Panel (구독 패널 열기)
```

#### 방법 2: 명령 팔레트를 통한 접근
```
Ctrl+Shift+P (또는 Cmd+Shift+P on Mac)
→ "Kiro: Open Subscription Management"
→ Enter
```

#### 방법 3: 사이드바 아이콘
- Kiro IDE 좌측 사이드바에서 "Subscription" 아이콘 클릭

### 2. 사용자 초대 프로세스

#### Step 1: 초대 패널 열기

구독 관리 패널에서 "Invite Users" 또는 "팀 멤버 추가" 버튼 클릭

```
┌─────────────────────────────────────────┐
│  Subscription Management                │
├─────────────────────────────────────────┤
│                                         │
│  📊 Subscription Status                 │
│  ├─ Plan: Professional                  │
│  ├─ Users: 3/10                         │
│  └─ Renewal: 2026-03-27                 │
│                                         │
│  👥 Team Members                        │
│  ├─ [user1@example.com] - Owner         │
│  ├─ [user2@example.com] - Editor        │
│  └─ [user3@example.com] - Viewer        │
│                                         │
│  [+ Invite Users] [Manage Team]         │
│                                         │
└─────────────────────────────────────────┘
```

#### Step 2: 초대할 사용자 정보 입력

"Invite Users" 버튼 클릭 후 다음 정보 입력:

```
┌─────────────────────────────────────────┐
│  Invite Users to Subscription           │
├─────────────────────────────────────────┤
│                                         │
│  Email Address(es):                     │
│  ┌─────────────────────────────────┐   │
│  │ user@example.com                │   │
│  │ another@example.com             │   │
│  │ (한 줄에 하나씩 또는 쉼표로 구분) │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Role:                                  │
│  ○ Owner (모든 권한)                    │
│  ○ Editor (편집 권한)                   │
│  ● Viewer (읽기 권한)                   │
│                                         │
│  Message (선택사항):                    │
│  ┌─────────────────────────────────┐   │
│  │ Join our Kiro subscription!     │   │
│  └─────────────────────────────────┘   │
│                                         │
│  [Cancel] [Send Invitations]            │
│                                         │
└─────────────────────────────────────────┘
```

**입력 필드 설명**:

| 필드 | 설명 | 예시 |
|------|------|------|
| Email Address(es) | 초대할 사용자의 이메일 주소 | user@example.com |
| Role | 초대된 사용자의 권한 수준 | Owner, Editor, Viewer |
| Message | 초대 이메일에 포함될 메시지 | "Join our team!" |

#### Step 3: 초대 확인

초대 전 확인 화면:

```
┌─────────────────────────────────────────┐
│  Confirm Invitations                    │
├─────────────────────────────────────────┤
│                                         │
│  다음 사용자에게 초대를 보내시겠습니까? │
│                                         │
│  ✓ user@example.com (Editor)            │
│  ✓ another@example.com (Viewer)         │
│                                         │
│  [Cancel] [Send]                        │
│                                         │
└─────────────────────────────────────────┘
```

#### Step 4: 초대 완료

초대 전송 완료 메시지:

```
┌─────────────────────────────────────────┐
│  ✓ Invitations Sent Successfully        │
├─────────────────────────────────────────┤
│                                         │
│  2 invitations have been sent to:       │
│  • user@example.com                     │
│  • another@example.com                  │
│                                         │
│  Invitations expire in 7 days.          │
│  Users can accept invitations via:      │
│  1. Email link                          │
│  2. Kiro IDE notification               │
│  3. Subscription panel                  │
│                                         │
│  [Close]                                │
│                                         │
└─────────────────────────────────────────┘
```

### 3. 사용자 역할 및 권한

#### Owner (소유자)
- 모든 구독 설정 변경
- 팀 멤버 추가/제거
- 청구 정보 관리
- 구독 취소
- 감사 로그 접근

#### Editor (편집자)
- 프로젝트 생성/수정/삭제
- 팀 멤버 초대 (Owner 승인 필요)
- 공유 리소스 관리
- 감사 로그 읽기 전용

#### Viewer (뷰어)
- 프로젝트 읽기 전용
- 공유 리소스 접근
- 자신의 프롬프트 이력 조회

### 4. 초대 상태 관리

#### 초대 상태 확인

구독 관리 패널의 "Pending Invitations" 탭:

```
┌─────────────────────────────────────────┐
│  Pending Invitations                    │
├─────────────────────────────────────────┤
│                                         │
│  user@example.com                       │
│  ├─ Status: Pending                     │
│  ├─ Role: Editor                        │
│  ├─ Sent: 2026-02-27 10:30 AM          │
│  ├─ Expires: 2026-03-06 10:30 AM       │
│  └─ [Resend] [Cancel]                   │
│                                         │
│  another@example.com                    │
│  ├─ Status: Accepted                    │
│  ├─ Role: Viewer                        │
│  ├─ Accepted: 2026-02-27 11:15 AM      │
│  └─ [Change Role] [Remove]              │
│                                         │
└─────────────────────────────────────────┘
```

#### 초대 재전송

만료되기 전에 초대를 다시 전송:
1. 초대 항목에서 [Resend] 버튼 클릭
2. 확인 메시지 표시
3. 새 초대 이메일 전송

#### 초대 취소

초대를 취소하려면:
1. 초대 항목에서 [Cancel] 버튼 클릭
2. 확인 메시지 표시
3. 초대 상태가 "Cancelled"로 변경

### 5. 초대 수락 프로세스 (사용자 관점)

#### 방법 1: 이메일 링크

초대된 사용자가 받는 이메일:

```
From: Kiro Subscription <noreply@kiro.dev>
Subject: You're invited to join a Kiro subscription

Hi [User Name],

[Inviter Name] has invited you to join their Kiro subscription.

Plan: Professional
Role: Editor
Expires: 2026-03-06

[Accept Invitation] [View Details]

---
If you don't have a Kiro account, you'll be prompted to create one.
```

이메일의 [Accept Invitation] 링크 클릭 → 자동으로 Kiro IDE에서 수락 처리

#### 방법 2: Kiro IDE 알림

Kiro IDE 실행 시 알림:

```
┌─────────────────────────────────────────┐
│  🔔 New Subscription Invitation          │
├─────────────────────────────────────────┤
│                                         │
│  You've been invited to join a          │
│  Professional subscription.             │
│                                         │
│  Role: Editor                           │
│  Expires: 2026-03-06                    │
│                                         │
│  [Accept] [Decline] [View Details]      │
│                                         │
└─────────────────────────────────────────┘
```

#### 방법 3: 구독 패널

구독 관리 패널의 "Invitations" 탭에서 수락:

```
┌─────────────────────────────────────────┐
│  My Invitations                         │
├─────────────────────────────────────────┤
│                                         │
│  Professional Subscription              │
│  ├─ From: [Inviter Name]                │
│  ├─ Role: Editor                        │
│  ├─ Expires: 2026-03-06                 │
│  └─ [Accept] [Decline]                  │
│                                         │
└─────────────────────────────────────────┘
```

## 백엔드 통합

### AWS 리소스 연동

Kiro IDE의 구독 관리 기능은 다음 AWS 리소스와 연동됩니다:

#### 1. S3 (bos-ai-kiro-logs)
- 사용자 프롬프트 및 메타데이터 저장
- 구독 사용 현황 데이터 저장
- 감사 로그 저장

#### 2. Secrets Manager
- API 키 관리
- 데이터베이스 자격증명
- S3 구성 정보

#### 3. Lambda Functions
- **Prompt Processor**: 사용자 프롬프트 처리
- **Metadata Analyzer**: 메타데이터 분석 및 저장

#### 4. EventBridge
- **Prompt Received**: 프롬프트 수신 이벤트
- **Prompt Error**: 오류 이벤트
- **All Events**: 모든 이벤트 로깅

#### 5. SNS & CloudWatch
- 오류 알림
- 성능 모니터링
- 사용량 추적

### 데이터 흐름

```
User Invitation
      │
      ▼
Kiro IDE UI
      │
      ├─ Validate Email
      ├─ Check Subscription Quota
      └─ Generate Invitation Token
            │
            ▼
      Kiro Backend API
            │
            ├─ Store Invitation (Database)
            ├─ Send Email (SES)
            └─ Log Event (EventBridge)
                  │
                  ▼
            AWS Infrastructure
                  │
                  ├─ S3: Store invitation metadata
                  ├─ Lambda: Process invitation
                  ├─ EventBridge: Log event
                  └─ SNS: Send notifications
```

## 모니터링 및 관리

### 구독 사용량 모니터링

구독 관리 패널의 "Usage" 탭:

```
┌─────────────────────────────────────────┐
│  Subscription Usage                     │
├─────────────────────────────────────────┤
│                                         │
│  Team Members: 3/10                     │
│  ├─ Active: 3                           │
│  ├─ Pending: 1                          │
│  └─ Invited: 2                          │
│                                         │
│  Prompts (This Month): 1,234/10,000     │
│  ├─ Used: 12.3%                         │
│  └─ Remaining: 8,766                    │
│                                         │
│  Storage: 2.5 GB / 100 GB               │
│  ├─ Used: 2.5%                          │
│  └─ Remaining: 97.5 GB                  │
│                                         │
│  API Calls: 45,678 / 100,000            │
│  ├─ Used: 45.7%                         │
│  └─ Remaining: 54,322                   │
│                                         │
└─────────────────────────────────────────┘
```

### 감사 로그

구독 관리 패널의 "Audit Log" 탭:

```
┌─────────────────────────────────────────┐
│  Audit Log                              │
├─────────────────────────────────────────┤
│                                         │
│  2026-02-27 11:30 AM                    │
│  └─ user@example.com invited            │
│     Role: Editor                        │
│     By: owner@example.com               │
│                                         │
│  2026-02-27 11:15 AM                    │
│  └─ another@example.com accepted        │
│     Role: Viewer                        │
│                                         │
│  2026-02-27 10:30 AM                    │
│  └─ Subscription upgraded               │
│     Plan: Professional                  │
│     By: owner@example.com               │
│                                         │
│  [Export Log] [Filter] [Search]         │
│                                         │
└─────────────────────────────────────────┘
```

## 문제 해결

### 문제 1: 초대 이메일을 받지 못함

**증상**: 초대 이메일이 도착하지 않음

**해결 방법**:
1. 스팸 폴더 확인
2. 이메일 주소 확인 (오타 여부)
3. 초대 재전송 ([Resend] 버튼)
4. 이메일 필터 설정 확인

### 문제 2: 초대 수락 실패

**증상**: "Accept Invitation" 클릭 후 오류 발생

**해결 방법**:
1. Kiro IDE 재시작
2. 인터넷 연결 확인
3. 초대 만료 여부 확인 (7일 이내)
4. 계정 로그인 상태 확인

### 문제 3: 팀 멤버 추가 불가

**증상**: "Invite Users" 버튼이 비활성화됨

**해결 방법**:
1. 구독 플랜 확인 (팀 멤버 수 제한)
2. 사용자 역할 확인 (Owner만 초대 가능)
3. 구독 상태 확인 (활성 상태 필요)
4. 구독 갱신 여부 확인

### 문제 4: 역할 변경 불가

**증상**: 팀 멤버의 역할을 변경할 수 없음

**해결 방법**:
1. Owner 권한 확인
2. 자신의 역할은 변경 불가 (다른 Owner에게 요청)
3. 팀 멤버 상태 확인 (Accepted 상태만 변경 가능)

## 보안 고려사항

### 초대 토큰 보안
- 초대 토큰은 암호화되어 저장
- 토큰은 7일 후 자동 만료
- 토큰은 일회용 (수락 후 무효화)

### 이메일 보안
- 모든 초대 이메일은 HTTPS를 통해 전송
- 이메일 주소는 암호화되어 저장
- 초대 링크는 서명되어 위변조 방지

### 접근 제어
- Owner만 팀 멤버 관리 가능
- 각 사용자는 자신의 역할에 따른 권한만 보유
- 모든 작업은 감사 로그에 기록

## 다음 단계

1. ✅ Kiro 구독 인프라 배포 완료
2. ✅ 사용자 초대 방식 결정 (Kiro 자체 기능)
3. ⏳ 팀 멤버 초대 및 구독 활성화
4. ⏳ 사용 현황 모니터링
5. ⏳ 청구 및 결제 설정

## 참고 자료

- [Kiro IDE 공식 문서](https://docs.kiro.dev)
- [Kiro 구독 관리 가이드](https://docs.kiro.dev/subscription)
- [AWS S3 문서](https://docs.aws.amazon.com/s3/)
- [AWS Lambda 문서](https://docs.aws.amazon.com/lambda/)

