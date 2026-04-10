"""
RTL OpenSearch Index 생성 스크립트
- AOSS(OpenSearch Serverless)는 Terraform local-exec 미사용
- SigV4 인증(requests-aws4auth)으로 data plane 인덱스 생성
- Requirements: 3.2, 3.3, 3.4

사용법:
  export OPENSEARCH_ENDPOINT=https://xxxx.us-east-1.aoss.amazonaws.com
  export AWS_REGION=us-east-1
  python scripts/create-opensearch-index.py
"""

import json
import os
import sys

import boto3
import requests
from requests_aws4auth import AWS4Auth

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
INDEX_NAME = os.environ.get("RTL_INDEX_NAME", "rtl-knowledge-base-index")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# AOSS Vector Search 컬렉션은 k-NN이 암묵적으로 활성화됨.
# settings.index.knn을 명시하면 IllegalArgumentException 발생 가능.
# mappings의 knn_vector 타입 정의만으로 충분.
INDEX_BODY = {
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "engine": "faiss",
                    "space_type": "l2",
                    "name": "hnsw",
                },
            },
            "module_name":    {"type": "keyword"},
            "parent_module":  {"type": "keyword"},
            "port_list":      {"type": "text"},
            "parameter_list": {"type": "text"},
            "instance_list":  {"type": "text"},
            "file_path":      {"type": "keyword"},
            "parsed_summary": {"type": "text"},
        }
    }
}


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    if not OPENSEARCH_ENDPOINT:
        print("ERROR: OPENSEARCH_ENDPOINT 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    # SigV4 인증 설정
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    auth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        AWS_REGION,
        "aoss",
        session_token=credentials.token,
    )

    url = f"{OPENSEARCH_ENDPOINT.rstrip('/')}/{INDEX_NAME}"

    # 인덱스 존재 여부 확인
    response = requests.head(url, auth=auth, timeout=30)
    if response.status_code == 200:
        print(f"인덱스 '{INDEX_NAME}'가 이미 존재합니다. 건너뜁니다.")
        return

    # 인덱스 생성
    print(f"인덱스 '{INDEX_NAME}' 생성 중...")
    response = requests.put(
        url,
        auth=auth,
        json=INDEX_BODY,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    if response.status_code in (200, 201):
        print(f"인덱스 '{INDEX_NAME}' 생성 완료.")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"ERROR: 인덱스 생성 실패 (HTTP {response.status_code})")
        print(response.text)
        sys.exit(1)


if __name__ == "__main__":
    main()
