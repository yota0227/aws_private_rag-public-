"""
AWS Lambda Document Processor for Bedrock RAG System

This Lambda function processes documents uploaded to S3, applies appropriate chunking
strategies based on document type, and initiates Bedrock Knowledge Base ingestion jobs.

Document Types and Chunking Strategies:
- RTL (Verilog/VHDL): Semantic chunking preserving module/function structure
- Specification: Hierarchical chunking based on section markers
- Diagram: Fixed chunking with text extraction
- Text: Semantic chunking with sentence boundaries
"""

import json
import logging
import os
import re
from typing import Dict, List, Any, Optional
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger.setLevel(getattr(logging, log_level))

# Initialize AWS clients
s3_client = boto3.client('s3')
bedrock_agent_client = boto3.client('bedrock-agent')

# Environment variables
DESTINATION_BUCKET = os.environ.get('DESTINATION_BUCKET')
SOURCE_BUCKET = os.environ.get('SOURCE_BUCKET')
KMS_KEY_ARN = os.environ.get('KMS_KEY_ARN')
KNOWLEDGE_BASE_ID = os.environ.get('KNOWLEDGE_BASE_ID', '')
DATA_SOURCE_ID = os.environ.get('DATA_SOURCE_ID', '')

# Chunking strategy configuration
CHUNKING_STRATEGIES = {
    "rtl": {
        "type": "semantic",
        "preserve_structure": True,
        "chunk_size": 2000,
        "overlap": 200,
        "delimiters": ["module", "endmodule", "function", "endfunction", "task", "endtask"]
    },
    "spec": {
        "type": "hierarchical",
        "chunk_size": 1500,
        "overlap": 150,
        "section_markers": ["#", "##", "###", "####"]
    },
    "diagram": {
        "type": "fixed",
        "chunk_size": 1000,
        "overlap": 0,
        "extract_text": True
    },
    "text": {
        "type": "semantic",
        "chunk_size": 1000,
        "overlap": 100,
        "sentence_boundary": True
    }
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for processing S3 events.
    
    Args:
        event: S3 event notification
        context: Lambda context object
        
    Returns:
        Response dictionary with status and processing results
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Parse S3 event
        records = event.get('Records', [])
        if not records:
            logger.warning("No records found in event")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No records to process'})
            }
        
        results = []
        for record in records:
            try:
                result = process_s3_record(record)
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing record: {str(e)}", exc_info=True)
                results.append({
                    'status': 'error',
                    'error': str(e)
                })
        
        # Determine overall status
        success_count = sum(1 for r in results if r.get('status') == 'success')
        total_count = len(results)
        
        return {
            'statusCode': 200 if success_count == total_count else 207,
            'body': json.dumps({
                'message': f'Processed {success_count}/{total_count} records successfully',
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


def process_s3_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single S3 event record.
    
    Args:
        record: S3 event record
        
    Returns:
        Processing result dictionary
    """
    # Extract S3 information
    s3_info = record.get('s3', {})
    bucket_name = s3_info.get('bucket', {}).get('name')
    object_key = unquote_plus(s3_info.get('object', {}).get('key', ''))
    object_size = s3_info.get('object', {}).get('size', 0)
    
    logger.info(f"Processing object: s3://{bucket_name}/{object_key} (size: {object_size} bytes)")
    
    # Get object metadata
    try:
        metadata = get_object_metadata(bucket_name, object_key)
    except ClientError as e:
        logger.error(f"Failed to get object metadata: {str(e)}")
        raise
    
    # Detect document type
    document_type = detect_document_type(object_key, metadata)
    logger.info(f"Detected document type: {document_type}")
    
    # Get chunking strategy
    chunking_strategy = get_chunking_strategy(document_type, metadata)
    logger.info(f"Using chunking strategy: {chunking_strategy['type']}")
    
    # For now, we'll just log the chunking strategy
    # In a full implementation, we would:
    # 1. Download the document
    # 2. Apply the chunking strategy
    # 3. Upload chunks to a processing location
    # 4. Initiate Bedrock ingestion job
    
    # Since Bedrock Knowledge Base handles chunking automatically,
    # we'll just initiate the ingestion job if configured
    if KNOWLEDGE_BASE_ID and DATA_SOURCE_ID:
        try:
            ingestion_job_id = initiate_bedrock_ingestion(
                knowledge_base_id=KNOWLEDGE_BASE_ID,
                data_source_id=DATA_SOURCE_ID
            )
            logger.info(f"Initiated Bedrock ingestion job: {ingestion_job_id}")
            
            return {
                'status': 'success',
                'bucket': bucket_name,
                'key': object_key,
                'document_type': document_type,
                'chunking_strategy': chunking_strategy['type'],
                'ingestion_job_id': ingestion_job_id
            }
        except Exception as e:
            logger.error(f"Failed to initiate Bedrock ingestion: {str(e)}")
            raise
    else:
        logger.info("KNOWLEDGE_BASE_ID or DATA_SOURCE_ID not configured, skipping ingestion")
        return {
            'status': 'success',
            'bucket': bucket_name,
            'key': object_key,
            'document_type': document_type,
            'chunking_strategy': chunking_strategy['type'],
            'message': 'Document processed, ingestion not configured'
        }


def get_object_metadata(bucket: str, key: str) -> Dict[str, str]:
    """
    Get S3 object metadata.
    
    Args:
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Dictionary of metadata
    """
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        return response.get('Metadata', {})
    except ClientError as e:
        logger.error(f"Error getting object metadata: {str(e)}")
        raise


def detect_document_type(object_key: str, metadata: Dict[str, str]) -> str:
    """
    Detect document type based on file extension and metadata.
    
    Args:
        object_key: S3 object key
        metadata: S3 object metadata
        
    Returns:
        Document type string (rtl, spec, diagram, text)
    """
    # Check metadata first
    if 'document-type' in metadata:
        return metadata['document-type']
    
    # Detect from file extension
    key_lower = object_key.lower()
    
    # RTL files
    if any(key_lower.endswith(ext) for ext in ['.v', '.vh', '.sv', '.vhd', '.vhdl']):
        return 'rtl'
    
    # Specification files
    if any(key_lower.endswith(ext) for ext in ['.md', '.rst', '.adoc', '.tex']):
        return 'spec'
    
    # Diagram files
    if any(key_lower.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf', '.svg']):
        return 'diagram'
    
    # Default to text
    return 'text'


def get_chunking_strategy(document_type: str, metadata: Dict[str, str]) -> Dict[str, Any]:
    """
    Get chunking strategy for document type.
    
    Args:
        document_type: Type of document
        metadata: S3 object metadata
        
    Returns:
        Chunking strategy configuration
    """
    # Check if metadata specifies a chunking strategy
    if 'chunking-strategy' in metadata:
        strategy_name = metadata['chunking-strategy']
        if strategy_name in CHUNKING_STRATEGIES:
            return CHUNKING_STRATEGIES[strategy_name]
    
    # Return default strategy for document type
    return CHUNKING_STRATEGIES.get(document_type, CHUNKING_STRATEGIES['text'])


def chunk_rtl_document(content: str, strategy: Dict[str, Any]) -> List[str]:
    """
    Apply semantic chunking to RTL documents, preserving module/function structure.
    
    Args:
        content: Document content
        strategy: Chunking strategy configuration
        
    Returns:
        List of text chunks
    """
    chunks = []
    delimiters = strategy.get('delimiters', [])
    chunk_size = strategy.get('chunk_size', 2000)
    overlap = strategy.get('overlap', 200)
    
    # Split by module boundaries
    pattern = '|'.join(re.escape(d) for d in delimiters)
    sections = re.split(f'({pattern})', content, flags=re.IGNORECASE)
    
    current_chunk = ""
    for section in sections:
        if len(current_chunk) + len(section) <= chunk_size:
            current_chunk += section
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # Start new chunk with overlap
            if overlap > 0 and current_chunk:
                current_chunk = current_chunk[-overlap:] + section
            else:
                current_chunk = section
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def chunk_spec_document(content: str, strategy: Dict[str, Any]) -> List[str]:
    """
    Apply hierarchical chunking to specification documents based on section markers.
    
    Args:
        content: Document content
        strategy: Chunking strategy configuration
        
    Returns:
        List of text chunks
    """
    chunks = []
    section_markers = strategy.get('section_markers', ['#'])
    chunk_size = strategy.get('chunk_size', 1500)
    overlap = strategy.get('overlap', 150)
    
    # Split by section markers
    lines = content.split('\n')
    current_chunk = ""
    current_section = ""
    
    for line in lines:
        # Check if line is a section marker
        is_section = any(line.strip().startswith(marker) for marker in section_markers)
        
        if is_section and current_chunk and len(current_chunk) > chunk_size:
            chunks.append(current_chunk)
            # Start new chunk with section context
            current_chunk = current_section + "\n" + line + "\n"
            current_section = line
        else:
            current_chunk += line + "\n"
            if is_section:
                current_section = line
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def chunk_text_document(content: str, strategy: Dict[str, Any]) -> List[str]:
    """
    Apply semantic chunking to text documents with sentence boundaries.
    
    Args:
        content: Document content
        strategy: Chunking strategy configuration
        
    Returns:
        List of text chunks
    """
    chunks = []
    chunk_size = strategy.get('chunk_size', 1000)
    overlap = strategy.get('overlap', 100)
    
    # Split by sentences
    sentences = re.split(r'(?<=[.!?])\s+', content)
    
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # Start new chunk with overlap
            if overlap > 0 and current_chunk:
                words = current_chunk.split()
                overlap_text = " ".join(words[-overlap:]) if len(words) > overlap else current_chunk
                current_chunk = overlap_text + " " + sentence + " "
            else:
                current_chunk = sentence + " "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def initiate_bedrock_ingestion(knowledge_base_id: str, data_source_id: str) -> str:
    """
    Initiate Bedrock Knowledge Base ingestion job with retry logic.
    
    Args:
        knowledge_base_id: Bedrock Knowledge Base ID
        data_source_id: Data source ID
        
    Returns:
        Ingestion job ID
        
    Raises:
        ClientError: If ingestion job fails after retries
    """
    max_retries = 3
    base_backoff = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Initiating ingestion job (attempt {attempt + 1}/{max_retries})")
            logger.info(f"Knowledge Base ID: {knowledge_base_id}")
            logger.info(f"Data Source ID: {data_source_id}")
            
            # Start ingestion job
            response = bedrock_agent_client.start_ingestion_job(
                knowledgeBaseId=knowledge_base_id,
                dataSourceId=data_source_id,
                description=f"Automated ingestion triggered by Lambda document processor"
            )
            
            ingestion_job = response.get('ingestionJob', {})
            ingestion_job_id = ingestion_job.get('ingestionJobId')
            status = ingestion_job.get('status')
            
            logger.info(f"Ingestion job started successfully")
            logger.info(f"Job ID: {ingestion_job_id}")
            logger.info(f"Status: {status}")
            
            # Publish CloudWatch metric
            publish_ingestion_metric('IngestionJobStarted', 1)
            
            return ingestion_job_id
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', '')
            
            logger.warning(f"Attempt {attempt + 1} failed: {error_code} - {error_message}")
            
            # Check if error is retryable
            if error_code in ['ThrottlingException', 'ServiceUnavailableException', 'TooManyRequestsException']:
                if attempt < max_retries - 1:
                    # Exponential backoff
                    backoff_time = base_backoff * (2 ** attempt)
                    logger.info(f"Retrying in {backoff_time} seconds...")
                    import time
                    time.sleep(backoff_time)
                    continue
                else:
                    logger.error(f"Max retries exceeded for throttling error")
                    publish_ingestion_metric('IngestionJobFailed', 1)
                    raise
            else:
                # Non-retryable error
                logger.error(f"Non-retryable error: {error_code}")
                publish_ingestion_metric('IngestionJobFailed', 1)
                raise
        
        except Exception as e:
            logger.error(f"Unexpected error initiating ingestion: {str(e)}", exc_info=True)
            publish_ingestion_metric('IngestionJobFailed', 1)
            raise
    
    # Should not reach here, but just in case
    error_msg = f"Failed to start ingestion job after {max_retries} attempts"
    logger.error(error_msg)
    publish_ingestion_metric('IngestionJobFailed', 1)
    raise Exception(error_msg)


def publish_ingestion_metric(metric_name: str, value: float) -> None:
    """
    Publish custom CloudWatch metric for ingestion tracking.
    
    Args:
        metric_name: Name of the metric
        value: Metric value
    """
    try:
        cloudwatch = boto3.client('cloudwatch')
        cloudwatch.put_metric_data(
            Namespace='BedrockRAG/DocumentProcessor',
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': 'Count'
                }
            ]
        )
        logger.debug(f"Published metric: {metric_name} = {value}")
    except Exception as e:
        # Don't fail the Lambda if metric publishing fails
        logger.warning(f"Failed to publish metric {metric_name}: {str(e)}")


def get_ingestion_job_status(knowledge_base_id: str, data_source_id: str, ingestion_job_id: str) -> Dict[str, Any]:
    """
    Get the status of a Bedrock ingestion job.
    
    Args:
        knowledge_base_id: Bedrock Knowledge Base ID
        data_source_id: Data source ID
        ingestion_job_id: Ingestion job ID
        
    Returns:
        Ingestion job details
    """
    try:
        response = bedrock_agent_client.get_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id,
            ingestionJobId=ingestion_job_id
        )
        
        ingestion_job = response.get('ingestionJob', {})
        return {
            'job_id': ingestion_job.get('ingestionJobId'),
            'status': ingestion_job.get('status'),
            'started_at': ingestion_job.get('startedAt'),
            'updated_at': ingestion_job.get('updatedAt'),
            'statistics': ingestion_job.get('statistics', {})
        }
        
    except ClientError as e:
        logger.error(f"Failed to get ingestion job status: {str(e)}")
        raise
