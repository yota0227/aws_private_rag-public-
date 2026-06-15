# Kiro SSH 접속 가이드

작성일: 2026-02-27

## 개요

Kiro IDE를 원격 서버에 SSH로 접속하여 사용하는 방법을 설명합니다. 이를 통해 로컬 머신에 설치하지 않고도 클라우드 환경에서 Kiro를 사용할 수 있습니다.

## 사전 요구사항

### 클라이언트 (로컬 머신)
- SSH 클라이언트 설치
  - **Windows**: PuTTY, Git Bash, WSL, 또는 Windows 10+ 내장 OpenSSH
  - **macOS**: 기본 내장 (Terminal)
  - **Linux**: 기본 내장 (Terminal)
- 인터넷 연결
- 원격 서버 접속 정보 (IP, 포트, 사용자명, 키)

### 서버 (원격 머신)
- Kiro IDE 설치됨
- SSH 서버 실행 중
- 방화벽에서 SSH 포트 (기본 22) 열려있음
- 충분한 디스크 공간 (최소 2GB)
- Node.js 또는 필요한 런타임 설치

## SSH 접속 방법

### 1. 기본 SSH 접속

#### 명령어
```bash
ssh -i /path/to/private/key username@server_ip
```

#### 예시
```bash
# 기본 포트 (22) 사용
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100

# 커스텀 포트 사용
ssh -i ~/.ssh/kiro-key.pem -p 2222 ubuntu@192.168.1.100

# 호스트명 사용
ssh -i ~/.ssh/kiro-key.pem ubuntu@kiro-server.example.com
```

#### 파라미터 설명
| 파라미터 | 설명 | 예시 |
|---------|------|------|
| `-i` | 개인 키 파일 경로 | `~/.ssh/kiro-key.pem` |
| `-p` | SSH 포트 (기본값: 22) | `2222` |
| `username` | 원격 서버 사용자명 | `ubuntu`, `ec2-user` |
| `server_ip` | 서버 IP 또는 호스트명 | `192.168.1.100` |

### 2. SSH 설정 파일을 이용한 접속

#### SSH 설정 파일 생성

`~/.ssh/config` 파일 생성 또는 편집:

```bash
# macOS/Linux
nano ~/.ssh/config

# Windows (Git Bash)
nano ~/.ssh/config
```

#### 설정 파일 내용

```
Host kiro-server
    HostName 192.168.1.100
    User ubuntu
    IdentityFile ~/.ssh/kiro-key.pem
    Port 22
    StrictHostKeyChecking accept-new
    UserKnownHostsFile ~/.ssh/known_hosts

Host kiro-prod
    HostName kiro-prod.example.com
    User ubuntu
    IdentityFile ~/.ssh/kiro-prod-key.pem
    Port 2222
    StrictHostKeyChecking accept-new

Host kiro-dev
    HostName kiro-dev.example.com
    User ubuntu
    IdentityFile ~/.ssh/kiro-dev-key.pem
    Port 22
```

#### 설정 파일을 이용한 접속

```bash
# 설정 파일에 정의된 호스트로 접속
ssh kiro-server
ssh kiro-prod
ssh kiro-dev
```

### 3. SSH 키 생성 및 설정

#### 새로운 SSH 키 생성

```bash
# RSA 키 생성 (4096비트)
ssh-keygen -t rsa -b 4096 -f ~/.ssh/kiro-key -C "your-email@example.com"

# ED25519 키 생성 (더 안전함)
ssh-keygen -t ed25519 -f ~/.ssh/kiro-key -C "your-email@example.com"
```

#### 키 권한 설정

```bash
# 개인 키 권한 설정 (중요!)
chmod 600 ~/.ssh/kiro-key

# 공개 키 권한 설정
chmod 644 ~/.ssh/kiro-key.pub

# .ssh 디렉토리 권한 설정
chmod 700 ~/.ssh
```

#### 공개 키를 서버에 등록

```bash
# 방법 1: ssh-copy-id 사용 (권장)
ssh-copy-id -i ~/.ssh/kiro-key.pub -p 22 ubuntu@192.168.1.100

# 방법 2: 수동으로 복사
cat ~/.ssh/kiro-key.pub | ssh -p 22 ubuntu@192.168.1.100 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# 방법 3: 파일로 복사
scp -i ~/.ssh/kiro-key.pem ~/.ssh/kiro-key.pub ubuntu@192.168.1.100:~/
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100 "cat ~/kiro-key.pub >> ~/.ssh/authorized_keys && rm ~/kiro-key.pub"
```

## Kiro IDE SSH 접속 후 사용

### 1. Kiro 서버 상태 확인

```bash
# Kiro 프로세스 확인
ps aux | grep kiro

# Kiro 포트 확인 (기본값: 3000)
netstat -tlnp | grep 3000
# 또는
lsof -i :3000

# Kiro 로그 확인
tail -f ~/.kiro/logs/kiro.log
```

### 2. Kiro 서버 시작/중지

```bash
# Kiro 서버 시작
kiro start

# Kiro 서버 중지
kiro stop

# Kiro 서버 재시작
kiro restart

# Kiro 서버 상태 확인
kiro status
```

### 3. Kiro 설정 확인

```bash
# Kiro 설정 파일 위치
cat ~/.kiro/config.json

# Kiro 버전 확인
kiro --version

# Kiro 도움말
kiro --help
```

### 4. Kiro 작업 디렉토리 접근

```bash
# Kiro 작업 디렉토리로 이동
cd ~/kiro-workspace

# 파일 목록 확인
ls -la

# 파일 편집
nano file.ts

# 파일 생성
touch new-file.ts
```

## SSH 포트 포워딩

### 1. 로컬 포트 포워딩

Kiro 서버의 포트를 로컬 머신으로 포워딩:

```bash
# 기본 포트 포워딩
ssh -i ~/.ssh/kiro-key.pem -L 3000:localhost:3000 ubuntu@192.168.1.100

# 커스텀 포트 포워딩
ssh -i ~/.ssh/kiro-key.pem -L 8080:localhost:3000 ubuntu@192.168.1.100

# 백그라운드에서 실행
ssh -i ~/.ssh/kiro-key.pem -L 3000:localhost:3000 -N -f ubuntu@192.168.1.100
```

#### 포트 포워딩 후 접속

```bash
# 로컬 브라우저에서 접속
http://localhost:3000

# 또는 curl 사용
curl http://localhost:3000
```

### 2. 원격 포트 포워딩

로컬 머신의 포트를 원격 서버로 포워딩:

```bash
# 로컬 포트 8080을 원격 서버의 포트 3000으로 포워딩
ssh -i ~/.ssh/kiro-key.pem -R 3000:localhost:8080 ubuntu@192.168.1.100
```

### 3. 동적 포트 포워딩 (SOCKS 프록시)

```bash
# SOCKS 프록시 설정
ssh -i ~/.ssh/kiro-key.pem -D 1080 ubuntu@192.168.1.100

# 브라우저에서 SOCKS 프록시 설정
# SOCKS Host: localhost
# SOCKS Port: 1080
```

## SSH 터널을 통한 파일 전송

### 1. SCP (Secure Copy)

```bash
# 로컬에서 원격으로 파일 복사
scp -i ~/.ssh/kiro-key.pem /local/path/file.ts ubuntu@192.168.1.100:~/kiro-workspace/

# 원격에서 로컬로 파일 복사
scp -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100:~/kiro-workspace/file.ts /local/path/

# 디렉토리 복사 (재귀)
scp -i ~/.ssh/kiro-key.pem -r /local/path/dir ubuntu@192.168.1.100:~/kiro-workspace/

# 커스텀 포트 사용
scp -i ~/.ssh/kiro-key.pem -P 2222 /local/path/file.ts ubuntu@192.168.1.100:~/kiro-workspace/
```

### 2. SFTP (SSH File Transfer Protocol)

```bash
# SFTP 세션 시작
sftp -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100

# SFTP 명령어
sftp> ls                    # 원격 파일 목록
sftp> pwd                   # 원격 현재 디렉토리
sftp> cd kiro-workspace     # 원격 디렉토리 변경
sftp> get file.ts           # 원격 파일 다운로드
sftp> put file.ts           # 로컬 파일 업로드
sftp> quit                  # SFTP 종료
```

### 3. Rsync (동기화)

```bash
# 로컬에서 원격으로 동기화
rsync -avz -e "ssh -i ~/.ssh/kiro-key.pem" /local/path/ ubuntu@192.168.1.100:~/kiro-workspace/

# 원격에서 로컬로 동기화
rsync -avz -e "ssh -i ~/.ssh/kiro-key.pem" ubuntu@192.168.1.100:~/kiro-workspace/ /local/path/

# 삭제 옵션 포함
rsync -avz --delete -e "ssh -i ~/.ssh/kiro-key.pem" /local/path/ ubuntu@192.168.1.100:~/kiro-workspace/
```

## SSH 보안 설정

### 1. SSH 키 보안

```bash
# 개인 키 암호화 (기존 키)
ssh-keygen -p -f ~/.ssh/kiro-key

# 개인 키 권한 확인
ls -la ~/.ssh/kiro-key
# 출력: -rw------- (600)

# 공개 키 권한 확인
ls -la ~/.ssh/kiro-key.pub
# 출력: -rw-r--r-- (644)
```

### 2. SSH 설정 보안

```bash
# SSH 설정 파일 권한
chmod 600 ~/.ssh/config

# known_hosts 파일 권한
chmod 600 ~/.ssh/known_hosts
```

### 3. SSH 에이전트 사용

```bash
# SSH 에이전트 시작
eval "$(ssh-agent -s)"

# 개인 키 에이전트에 추가
ssh-add ~/.ssh/kiro-key

# 에이전트에 추가된 키 확인
ssh-add -l

# 에이전트에서 키 제거
ssh-add -d ~/.ssh/kiro-key

# 에이전트 종료
ssh-agent -k
```

### 4. SSH 설정 파일 보안 옵션

```
Host kiro-server
    HostName 192.168.1.100
    User ubuntu
    IdentityFile ~/.ssh/kiro-key.pem
    
    # 보안 옵션
    StrictHostKeyChecking accept-new
    UserKnownHostsFile ~/.ssh/known_hosts
    PasswordAuthentication no
    PubkeyAuthentication yes
    IdentitiesOnly yes
    
    # 연결 옵션
    ServerAliveInterval 60
    ServerAliveCountMax 3
    TCPKeepAlive yes
    
    # 압축 옵션
    Compression yes
    CompressionLevel 6
```

## 문제 해결

### 문제 1: 접속 거부 (Permission denied)

**증상**: `Permission denied (publickey)`

**해결**:
```bash
# 1. 개인 키 권한 확인
chmod 600 ~/.ssh/kiro-key

# 2. 공개 키가 서버에 등록되었는지 확인
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100 "cat ~/.ssh/authorized_keys"

# 3. SSH 디버그 모드로 확인
ssh -vvv -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100

# 4. 서버의 SSH 설정 확인
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100 "sudo cat /etc/ssh/sshd_config | grep -E 'PubkeyAuthentication|PasswordAuthentication'"
```

### 문제 2: 호스트 키 검증 실패

**증상**: `Host key verification failed`

**해결**:
```bash
# 1. known_hosts 파일에 호스트 추가
ssh-keyscan -H 192.168.1.100 >> ~/.ssh/known_hosts

# 2. 또는 처음 접속 시 yes 입력
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100
# Are you sure you want to continue connecting (yes/no)? yes

# 3. SSH 설정에서 자동 수락 설정
# ~/.ssh/config에 다음 추가:
# StrictHostKeyChecking accept-new
```

### 문제 3: 포트 연결 실패

**증상**: `Connection refused` 또는 `Connection timed out`

**해결**:
```bash
# 1. 서버 포트 확인
telnet 192.168.1.100 22

# 2. 방화벽 확인
sudo ufw status
sudo ufw allow 22/tcp

# 3. SSH 서비스 상태 확인
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100 "sudo systemctl status ssh"

# 4. SSH 서비스 재시작
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100 "sudo systemctl restart ssh"
```

### 문제 4: 느린 연결

**증상**: SSH 접속이 느림

**해결**:
```bash
# 1. DNS 조회 비활성화
ssh -i ~/.ssh/kiro-key.pem -o UseDNS=no ubuntu@192.168.1.100

# 2. 압축 활성화
ssh -i ~/.ssh/kiro-key.pem -C ubuntu@192.168.1.100

# 3. SSH 설정 파일에 추가
# ~/.ssh/config에 다음 추가:
# UseDNS no
# Compression yes
# CompressionLevel 6
```

### 문제 5: 연결 끊김

**증상**: SSH 연결이 자주 끊김

**해결**:
```bash
# SSH 설정 파일에 다음 추가
# ~/.ssh/config에 다음 추가:
# ServerAliveInterval 60
# ServerAliveCountMax 3
# TCPKeepAlive yes

# 또는 명령어로 실행
ssh -i ~/.ssh/kiro-key.pem -o ServerAliveInterval=60 -o ServerAliveCountMax=3 ubuntu@192.168.1.100
```

## 고급 사용법

### 1. SSH 멀티플렉싱

여러 SSH 연결을 하나의 연결로 통합:

```bash
# SSH 설정 파일에 추가
Host kiro-server
    HostName 192.168.1.100
    User ubuntu
    IdentityFile ~/.ssh/kiro-key.pem
    
    # 멀티플렉싱 설정
    ControlMaster auto
    ControlPath ~/.ssh/control-%h-%p-%r
    ControlPersist 600
```

### 2. SSH 배스천 호스트 (점프 호스트)

중간 서버를 거쳐 접속:

```bash
# 명령어로 실행
ssh -i ~/.ssh/kiro-key.pem -J ubuntu@bastion.example.com ubuntu@192.168.1.100

# SSH 설정 파일에 추가
Host kiro-server
    HostName 192.168.1.100
    User ubuntu
    IdentityFile ~/.ssh/kiro-key.pem
    ProxyJump bastion

Host bastion
    HostName bastion.example.com
    User ubuntu
    IdentityFile ~/.ssh/bastion-key.pem
```

### 3. SSH 자동 로그인 스크립트

```bash
#!/bin/bash
# kiro-connect.sh

SERVER="192.168.1.100"
USER="ubuntu"
KEY="~/.ssh/kiro-key.pem"
PORT="22"

# SSH 접속
ssh -i "$KEY" -p "$PORT" "$USER@$SERVER"
```

사용:
```bash
chmod +x kiro-connect.sh
./kiro-connect.sh
```

### 4. SSH 배치 작업

```bash
# 원격 서버에서 명령 실행
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100 "cd ~/kiro-workspace && npm run build"

# 여러 명령 실행
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100 << 'EOF'
cd ~/kiro-workspace
npm install
npm run build
npm start
EOF

# 로컬 스크립트를 원격에서 실행
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100 'bash -s' < local-script.sh
```

## Windows에서 SSH 사용

### 1. Windows 10+ 내장 OpenSSH

```powershell
# SSH 클라이언트 설치 확인
Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH*'

# SSH 클라이언트 설치
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0

# SSH 접속
ssh -i C:\Users\YourName\.ssh\kiro-key.pem ubuntu@192.168.1.100
```

### 2. Git Bash 사용

```bash
# Git Bash 설치 후
ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100
```

### 3. PuTTY 사용

```
1. PuTTY 다운로드 및 설치
2. PuTTYgen으로 개인 키 변환 (.pem → .ppk)
3. PuTTY 실행
4. Session 탭에서 Host Name 입력
5. Connection > SSH > Auth에서 개인 키 파일 선택
6. Open 클릭
```

## macOS/Linux 팁

### 1. SSH 키 체인 저장

```bash
# macOS: SSH 키를 Keychain에 저장
ssh-add -K ~/.ssh/kiro-key

# Linux: SSH 에이전트에 저장
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/kiro-key
```

### 2. SSH 별칭 생성

```bash
# ~/.bashrc 또는 ~/.zshrc에 추가
alias kiro-ssh='ssh -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100'
alias kiro-sftp='sftp -i ~/.ssh/kiro-key.pem ubuntu@192.168.1.100'

# 사용
kiro-ssh
kiro-sftp
```

### 3. SSH 연결 모니터링

```bash
# 활성 SSH 연결 확인
ps aux | grep ssh

# SSH 포트 확인
netstat -tlnp | grep ssh

# SSH 로그 확인
tail -f /var/log/auth.log  # Linux
log stream --predicate 'process == "sshd"'  # macOS
```

## 성능 최적화

### 1. SSH 연결 속도 개선

```bash
# 압축 활성화
ssh -i ~/.ssh/kiro-key.pem -C ubuntu@192.168.1.100

# 암호화 알고리즘 지정
ssh -i ~/.ssh/kiro-key.pem -c aes128-ctr ubuntu@192.168.1.100

# SSH 설정 파일에 추가
Host kiro-server
    Compression yes
    CompressionLevel 6
    Ciphers aes128-ctr,aes192-ctr,aes256-ctr
```

### 2. 대역폭 최적화

```bash
# 대역폭 제한
ssh -i ~/.ssh/kiro-key.pem -l 1000 ubuntu@192.168.1.100

# SCP 대역폭 제한
scp -i ~/.ssh/kiro-key.pem -l 1000 /local/file ubuntu@192.168.1.100:~/
```

## 체크리스트

- ✅ SSH 클라이언트 설치
- ✅ SSH 키 생성 및 설정
- ✅ 공개 키를 서버에 등록
- ✅ SSH 설정 파일 생성
- ✅ 권한 설정 (600, 644, 700)
- ✅ SSH 에이전트 설정
- ✅ 포트 포워딩 설정 (필요시)
- ✅ 방화벽 설정 확인
- ✅ 보안 옵션 설정
- ✅ 연결 테스트

## 참고 자료

### 공식 문서
- [OpenSSH 공식 문서](https://man.openbsd.org/ssh)
- [SSH 보안 가이드](https://www.ssh.com/ssh/security)
- [Kiro IDE 공식 문서](https://docs.kiro.dev)

### 유용한 도구
- [PuTTY](https://www.putty.org/) - Windows SSH 클라이언트
- [MobaXterm](https://mobaxterm.mobatek.net/) - 고급 SSH 클라이언트
- [Termius](https://www.termius.com/) - 크로스 플랫폼 SSH 클라이언트

### 보안 리소스
- [SSH 키 보안 가이드](https://wiki.archlinux.org/title/SSH_keys)
- [SSH 설정 보안](https://linux-audit.com/audit-and-harden-your-ssh-configuration/)

---

**작성일**: 2026-02-27
**최종 수정**: 2026-02-27
**버전**: 1.0

