"""
QuickSight RAG Connector Lambda 단위 테스트

테스트 항목:
  - 응답 변환 (_transform_response)
  - 캐시 히트/미스/만료
  - RAG API 에러 처리
  - 하드코딩 자격 증명 미포함 검증
"""

import json
import os
import time
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

os.environ.setdefault("RAG_API_ENDPOINT", "https://rag.corp.bos-semi.com")
os.environ.setdefault("CACHE_BUCKET", "test-bucket")
os.environ.setdefault("CACHE_TTL_SECONDS", "3600")

import handler


class TestTransformResponse(unittest.TestCase):

    def test_basic_transform(self):
        body = {"items": [{"query_id": "q-001", "query_text": "SoC 설계", "response_time_ms": 1200, "citation_count": 3, "search_type": "semantic", "timestamp": "2026-04-01T10:00:00Z"}]}
        result = handler._transform_response(body, "rag_usage_stats")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["query_id"], "q-001")
        self.assertEqual(result[0]["query_pattern"], "rag_usage_stats")

    def test_empty_items(self):
        self.assertEqual(handler._transform_response({}, "test"), [])

    def test_data_key_fallback(self):
        body = {"data": [{"query_id": "q-002"}]}
        result = handler._transform_response(body, "test")
        self.assertEqual(result[0]["query_id"], "q-002")

    def test_required_fields_present(self):
        body = {"items": [{}]}
        result = handler._transform_response(body, "test")
        required = {"query_id", "query_text", "response_time_ms", "citation_count", "search_type", "timestamp", "query_pattern"}
        self.assertEqual(set(result[0].keys()), required)

    def test_type_coercion(self):
        body = {"items": [{"response_time_ms": "500", "citation_count": "2"}]}
        result = handler._transform_response(body, "test")
        self.assertIsInstance(result[0]["response_time_ms"], int)
        self.assertIsInstance(result[0]["citation_count"], int)


class TestCache(unittest.TestCase):

    def _s3_resp(self, data, cached_at=None):
        payload = {"cached_at": cached_at or time.time(), "ttl_seconds": 3600, "data": data}
        return {"Body": BytesIO(json.dumps(payload).encode())}

    @patch("handler.s3")
    def test_cache_hit(self, mock_s3):
        data = [{"query_id": "q-001"}]
        mock_s3.get_object.return_value = self._s3_resp(data)
        self.assertEqual(handler._read_cache("cache/abc/data.json"), data)

    @patch("handler.s3")
    def test_cache_miss_no_such_key(self, mock_s3):
        from botocore.exceptions import ClientError
        mock_s3.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey", "Message": ""}}, "GetObject")
        self.assertIsNone(handler._read_cache("cache/abc/data.json"))

    @patch("handler.s3")
    def test_cache_expired(self, mock_s3):
        mock_s3.get_object.return_value = self._s3_resp([{"query_id": "old"}], cached_at=time.time() - 7200)
        self.assertIsNone(handler._read_cache("cache/abc/data.json"))

    @patch("handler.s3")
    def test_cache_write_success(self, mock_s3):
        mock_s3.put_object.return_value = {}
        handler._write_cache("cache/abc/data.json", [])
        mock_s3.put_object.assert_called_once()

    @patch("handler.s3")
    def test_cache_write_failure_ignored(self, mock_s3):
        from botocore.exceptions import ClientError
        mock_s3.put_object.side_effect = ClientError({"Error": {"Code": "AccessDenied", "Message": ""}}, "PutObject")
        handler._write_cache("cache/abc/data.json", [])  # 예외 없이 통과


class TestRAGAPIError(unittest.TestCase):

    @patch("handler.urllib.request.urlopen")
    @patch("handler._publish_metric")
    def test_http_error_retries_and_raises(self, mock_metric, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(url="", code=500, msg="Error", hdrs=None, fp=None)
        with self.assertRaises(urllib.error.HTTPError):
            handler._fetch_from_rag_api("rag_usage_stats")
        self.assertEqual(mock_urlopen.call_count, 3)
        mock_metric.assert_called_with("RAGAPIError", 1)

    @patch("handler.urllib.request.urlopen")
    @patch("handler._publish_metric")
    def test_success_returns_data(self, mock_metric, mock_urlopen):
        body = {"items": [{"query_id": "q-001"}]}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = handler._fetch_from_rag_api("rag_usage_stats")
        self.assertEqual(len(result), 1)
        mock_metric.assert_called_with("RAGAPISuccess", 1)


class TestLambdaHandler(unittest.TestCase):

    @patch("handler.get_data_with_cache")
    def test_success(self, mock_get):
        mock_get.return_value = [{"query_id": "q-001"}]
        result = handler.lambda_handler({"query_pattern": "rag_usage_stats"}, None)
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["count"], 1)

    @patch("handler.get_data_with_cache")
    @patch("handler._publish_metric")
    def test_error_returns_empty(self, mock_metric, mock_get):
        mock_get.side_effect = Exception("RAG API down")
        result = handler.lambda_handler({}, None)
        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["data"], [])
        self.assertIn("error", result)


class TestNoHardcodedCredentials(unittest.TestCase):

    def test_no_aws_credentials(self):
        with open(os.path.join(os.path.dirname(__file__), "handler.py"), encoding="utf-8") as f:
            source = f.read()
        for pattern in ["AKIA", "aws_access_key_id", "aws_secret_access_key", "SecretAccessKey"]:
            self.assertNotIn(pattern, source, f"Found forbidden pattern: {pattern}")


if __name__ == "__main__":
    unittest.main()
