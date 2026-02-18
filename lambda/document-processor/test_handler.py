"""
Unit tests for Lambda document processor handler.

Tests cover:
- S3 event parsing
- Document type detection
- Chunking strategies for different document types
- Bedrock ingestion job initiation
- Error handling and retry logic
"""

import json
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

# Set environment variables before importing handler
os.environ['DESTINATION_BUCKET'] = 'test-destination-bucket'
os.environ['SOURCE_BUCKET'] = 'test-source-bucket'
os.environ['KMS_KEY_ARN'] = 'arn:aws:kms:us-east-1:123456789012:key/test-key'
os.environ['KNOWLEDGE_BASE_ID'] = 'test-kb-id'
os.environ['DATA_SOURCE_ID'] = 'test-ds-id'
os.environ['LOG_LEVEL'] = 'INFO'

import handler


class TestS3EventParsing(unittest.TestCase):
    """Test S3 event parsing functionality."""
    
    def test_parse_valid_s3_event(self):
        """Test parsing a valid S3 event."""
        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'test-file.txt', 'size': 1024}
                    }
                }
            ]
        }
        
        with patch.object(handler, 'process_s3_record', return_value={'status': 'success'}):
            result = handler.lambda_handler(event, None)
            
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertIn('message', body)
        self.assertIn('results', body)
    
    def test_parse_empty_event(self):
        """Test parsing an empty event."""
        event = {'Records': []}
        
        result = handler.lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertEqual(body['message'], 'No records to process')
    
    def test_parse_event_without_records(self):
        """Test parsing an event without Records key."""
        event = {}
        
        result = handler.lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 200)
        body = json.loads(result['body'])
        self.assertEqual(body['message'], 'No records to process')


class TestDocumentTypeDetection(unittest.TestCase):
    """Test document type detection functionality."""
    
    def test_detect_rtl_from_extension_verilog(self):
        """Test RTL detection from Verilog file extension."""
        doc_type = handler.detect_document_type('design.v', {})
        self.assertEqual(doc_type, 'rtl')
    
    def test_detect_rtl_from_extension_systemverilog(self):
        """Test RTL detection from SystemVerilog file extension."""
        doc_type = handler.detect_document_type('design.sv', {})
        self.assertEqual(doc_type, 'rtl')
    
    def test_detect_rtl_from_extension_vhdl(self):
        """Test RTL detection from VHDL file extension."""
        doc_type = handler.detect_document_type('design.vhd', {})
        self.assertEqual(doc_type, 'rtl')
    
    def test_detect_spec_from_extension_markdown(self):
        """Test specification detection from Markdown file extension."""
        doc_type = handler.detect_document_type('README.md', {})
        self.assertEqual(doc_type, 'spec')
    
    def test_detect_spec_from_extension_rst(self):
        """Test specification detection from reStructuredText file extension."""
        doc_type = handler.detect_document_type('docs.rst', {})
        self.assertEqual(doc_type, 'spec')
    
    def test_detect_diagram_from_extension_png(self):
        """Test diagram detection from PNG file extension."""
        doc_type = handler.detect_document_type('diagram.png', {})
        self.assertEqual(doc_type, 'diagram')
    
    def test_detect_diagram_from_extension_pdf(self):
        """Test diagram detection from PDF file extension."""
        doc_type = handler.detect_document_type('diagram.pdf', {})
        self.assertEqual(doc_type, 'diagram')
    
    def test_detect_text_default(self):
        """Test default text detection for unknown extensions."""
        doc_type = handler.detect_document_type('document.txt', {})
        self.assertEqual(doc_type, 'text')
    
    def test_detect_from_metadata(self):
        """Test document type detection from S3 metadata."""
        metadata = {'document-type': 'rtl'}
        doc_type = handler.detect_document_type('unknown.file', metadata)
        self.assertEqual(doc_type, 'rtl')
    
    def test_case_insensitive_detection(self):
        """Test case-insensitive file extension detection."""
        doc_type = handler.detect_document_type('DESIGN.V', {})
        self.assertEqual(doc_type, 'rtl')


class TestChunkingStrategies(unittest.TestCase):
    """Test chunking strategy selection and application."""
    
    def test_get_rtl_chunking_strategy(self):
        """Test getting RTL chunking strategy."""
        strategy = handler.get_chunking_strategy('rtl', {})
        self.assertEqual(strategy['type'], 'semantic')
        self.assertEqual(strategy['chunk_size'], 2000)
        self.assertEqual(strategy['overlap'], 200)
        self.assertIn('delimiters', strategy)
    
    def test_get_spec_chunking_strategy(self):
        """Test getting specification chunking strategy."""
        strategy = handler.get_chunking_strategy('spec', {})
        self.assertEqual(strategy['type'], 'hierarchical')
        self.assertEqual(strategy['chunk_size'], 1500)
        self.assertEqual(strategy['overlap'], 150)
        self.assertIn('section_markers', strategy)
    
    def test_get_diagram_chunking_strategy(self):
        """Test getting diagram chunking strategy."""
        strategy = handler.get_chunking_strategy('diagram', {})
        self.assertEqual(strategy['type'], 'fixed')
        self.assertEqual(strategy['chunk_size'], 1000)
        self.assertEqual(strategy['overlap'], 0)
    
    def test_get_text_chunking_strategy(self):
        """Test getting text chunking strategy."""
        strategy = handler.get_chunking_strategy('text', {})
        self.assertEqual(strategy['type'], 'semantic')
        self.assertEqual(strategy['chunk_size'], 1000)
        self.assertEqual(strategy['overlap'], 100)
    
    def test_override_strategy_from_metadata(self):
        """Test overriding chunking strategy from metadata."""
        metadata = {'chunking-strategy': 'spec'}
        strategy = handler.get_chunking_strategy('text', metadata)
        self.assertEqual(strategy['type'], 'hierarchical')
    
    def test_chunk_rtl_document(self):
        """Test RTL document chunking."""
        content = """
        module test_module;
            input wire clk;
            output reg data;
        endmodule
        
        module another_module;
            input wire reset;
        endmodule
        """
        strategy = handler.CHUNKING_STRATEGIES['rtl']
        chunks = handler.chunk_rtl_document(content, strategy)
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)
    
    def test_chunk_spec_document(self):
        """Test specification document chunking."""
        content = """
        # Main Title
        
        ## Section 1
        Content for section 1.
        
        ## Section 2
        Content for section 2.
        
        ### Subsection 2.1
        More content.
        """
        strategy = handler.CHUNKING_STRATEGIES['spec']
        chunks = handler.chunk_spec_document(content, strategy)
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)
    
    def test_chunk_text_document(self):
        """Test text document chunking."""
        content = """
        This is the first sentence. This is the second sentence.
        This is the third sentence. This is the fourth sentence.
        """
        strategy = handler.CHUNKING_STRATEGIES['text']
        chunks = handler.chunk_text_document(content, strategy)
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)


class TestBedrockIngestion(unittest.TestCase):
    """Test Bedrock ingestion job initiation."""
    
    @patch('handler.bedrock_agent_client')
    @patch('handler.publish_ingestion_metric')
    def test_initiate_ingestion_success(self, mock_metric, mock_client):
        """Test successful ingestion job initiation."""
        mock_client.start_ingestion_job.return_value = {
            'ingestionJob': {
                'ingestionJobId': 'test-job-id',
                'status': 'STARTING'
            }
        }
        
        job_id = handler.initiate_bedrock_ingestion('kb-id', 'ds-id')
        
        self.assertEqual(job_id, 'test-job-id')
        mock_client.start_ingestion_job.assert_called_once()
        mock_metric.assert_called_with('IngestionJobStarted', 1)
    
    @patch('handler.bedrock_agent_client')
    @patch('handler.publish_ingestion_metric')
    @patch('time.sleep')
    def test_initiate_ingestion_retry_on_throttling(self, mock_sleep, mock_metric, mock_client):
        """Test retry logic on throttling exception."""
        # First call raises throttling exception, second succeeds
        mock_client.start_ingestion_job.side_effect = [
            ClientError(
                {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                'StartIngestionJob'
            ),
            {
                'ingestionJob': {
                    'ingestionJobId': 'test-job-id',
                    'status': 'STARTING'
                }
            }
        ]
        
        job_id = handler.initiate_bedrock_ingestion('kb-id', 'ds-id')
        
        self.assertEqual(job_id, 'test-job-id')
        self.assertEqual(mock_client.start_ingestion_job.call_count, 2)
        mock_sleep.assert_called_once()
    
    @patch('handler.bedrock_agent_client')
    @patch('handler.publish_ingestion_metric')
    def test_initiate_ingestion_non_retryable_error(self, mock_metric, mock_client):
        """Test non-retryable error handling."""
        mock_client.start_ingestion_job.side_effect = ClientError(
            {'Error': {'Code': 'ValidationException', 'Message': 'Invalid input'}},
            'StartIngestionJob'
        )
        
        with self.assertRaises(ClientError):
            handler.initiate_bedrock_ingestion('kb-id', 'ds-id')
        
        mock_metric.assert_called_with('IngestionJobFailed', 1)
    
    @patch('handler.bedrock_agent_client')
    @patch('handler.publish_ingestion_metric')
    @patch('time.sleep')
    def test_initiate_ingestion_max_retries_exceeded(self, mock_sleep, mock_metric, mock_client):
        """Test max retries exceeded."""
        mock_client.start_ingestion_job.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'StartIngestionJob'
        )
        
        with self.assertRaises(ClientError):
            handler.initiate_bedrock_ingestion('kb-id', 'ds-id')
        
        self.assertEqual(mock_client.start_ingestion_job.call_count, 3)
        mock_metric.assert_called_with('IngestionJobFailed', 1)
    
    @patch('handler.bedrock_agent_client')
    def test_get_ingestion_job_status(self, mock_client):
        """Test getting ingestion job status."""
        mock_client.get_ingestion_job.return_value = {
            'ingestionJob': {
                'ingestionJobId': 'test-job-id',
                'status': 'COMPLETE',
                'startedAt': '2024-01-01T00:00:00Z',
                'updatedAt': '2024-01-01T00:05:00Z',
                'statistics': {
                    'numberOfDocumentsScanned': 10,
                    'numberOfDocumentsIndexed': 10
                }
            }
        }
        
        status = handler.get_ingestion_job_status('kb-id', 'ds-id', 'test-job-id')
        
        self.assertEqual(status['job_id'], 'test-job-id')
        self.assertEqual(status['status'], 'COMPLETE')
        self.assertIn('statistics', status)


class TestErrorHandling(unittest.TestCase):
    """Test error handling functionality."""
    
    @patch('handler.s3_client')
    def test_get_object_metadata_error(self, mock_s3):
        """Test error handling when getting object metadata fails."""
        mock_s3.head_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey', 'Message': 'Key not found'}},
            'HeadObject'
        )
        
        with self.assertRaises(ClientError):
            handler.get_object_metadata('bucket', 'key')
    
    @patch('handler.process_s3_record')
    def test_lambda_handler_partial_failure(self, mock_process):
        """Test Lambda handler with partial record failures."""
        mock_process.side_effect = [
            {'status': 'success'},
            Exception('Processing failed'),
            {'status': 'success'}
        ]
        
        event = {
            'Records': [
                {'s3': {'bucket': {'name': 'b1'}, 'object': {'key': 'k1'}}},
                {'s3': {'bucket': {'name': 'b2'}, 'object': {'key': 'k2'}}},
                {'s3': {'bucket': {'name': 'b3'}, 'object': {'key': 'k3'}}}
            ]
        }
        
        result = handler.lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 207)  # Multi-status
        body = json.loads(result['body'])
        self.assertIn('2/3', body['message'])
    
    def test_lambda_handler_unexpected_error(self):
        """Test Lambda handler with unexpected error."""
        event = None  # Invalid event
        
        result = handler.lambda_handler(event, None)
        
        self.assertEqual(result['statusCode'], 500)
        body = json.loads(result['body'])
        self.assertIn('error', body)


class TestCloudWatchMetrics(unittest.TestCase):
    """Test CloudWatch metrics publishing."""
    
    @patch('boto3.client')
    def test_publish_metric_success(self, mock_boto3):
        """Test successful metric publishing."""
        mock_cloudwatch = MagicMock()
        mock_boto3.return_value = mock_cloudwatch
        
        handler.publish_ingestion_metric('TestMetric', 1.0)
        
        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        self.assertEqual(call_args[1]['Namespace'], 'BedrockRAG/DocumentProcessor')
    
    @patch('boto3.client')
    def test_publish_metric_failure_does_not_raise(self, mock_boto3):
        """Test that metric publishing failure doesn't raise exception."""
        mock_cloudwatch = MagicMock()
        mock_cloudwatch.put_metric_data.side_effect = Exception('CloudWatch error')
        mock_boto3.return_value = mock_cloudwatch
        
        # Should not raise exception
        handler.publish_ingestion_metric('TestMetric', 1.0)


if __name__ == '__main__':
    unittest.main()
