# Document Processor Lambda Function

This Lambda function processes documents uploaded to S3 for the AWS Bedrock RAG system. It applies appropriate chunking strategies based on document type and initiates Bedrock Knowledge Base ingestion jobs.

## Features

- **Automatic Document Type Detection**: Detects document type from file extension or S3 metadata
- **Multiple Chunking Strategies**:
  - **RTL (Verilog/VHDL)**: Semantic chunking preserving module/function structure
  - **Specification**: Hierarchical chunking based on section markers
  - **Diagram**: Fixed chunking with text extraction support
  - **Text**: Semantic chunking with sentence boundaries
- **S3 Event-Driven**: Automatically triggered when documents are uploaded to S3
- **Error Handling**: Dead Letter Queue (DLQ) for failed invocations
- **Observability**: CloudWatch Logs and X-Ray tracing enabled

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DESTINATION_BUCKET` | S3 bucket for processed documents | Yes |
| `SOURCE_BUCKET` | S3 source bucket name | Yes |
| `KMS_KEY_ARN` | KMS key ARN for encryption | Yes |
| `KNOWLEDGE_BASE_ID` | Bedrock Knowledge Base ID | No |
| `DATA_SOURCE_ID` | Bedrock Data Source ID | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | No (default: INFO) |

## Document Type Detection

The function detects document types using the following logic:

1. **Check S3 Metadata**: If `document-type` metadata is present, use it
2. **File Extension Detection**:
   - RTL: `.v`, `.vh`, `.sv`, `.vhd`, `.vhdl`
   - Specification: `.md`, `.rst`, `.adoc`, `.tex`
   - Diagram: `.png`, `.jpg`, `.jpeg`, `.pdf`, `.svg`
   - Text: Default for all other files

## Chunking Strategies

### RTL Documents
- **Type**: Semantic
- **Chunk Size**: 2000 characters
- **Overlap**: 200 characters
- **Delimiters**: `module`, `endmodule`, `function`, `endfunction`, `task`, `endtask`
- **Preserves**: Code structure and module boundaries

### Specification Documents
- **Type**: Hierarchical
- **Chunk Size**: 1500 characters
- **Overlap**: 150 characters
- **Section Markers**: `#`, `##`, `###`, `####`
- **Preserves**: Document hierarchy and section context

### Diagram Documents
- **Type**: Fixed
- **Chunk Size**: 1000 characters
- **Overlap**: 0 characters
- **Features**: Text extraction support

### Text Documents
- **Type**: Semantic
- **Chunk Size**: 1000 characters
- **Overlap**: 100 characters
- **Boundaries**: Sentence boundaries
- **Preserves**: Sentence integrity

## S3 Metadata

You can control document processing by setting S3 object metadata:

```bash
aws s3 cp document.v s3://bucket/path/ \
  --metadata document-type=rtl,chunking-strategy=rtl
```

Supported metadata keys:
- `document-type`: Override automatic type detection (rtl, spec, diagram, text)
- `chunking-strategy`: Override default chunking strategy

## Deployment

The Lambda function is deployed via Terraform as part of the S3 pipeline module:

```hcl
module "s3_pipeline" {
  source = "./modules/ai-workload/s3-pipeline"
  
  lambda_function_name = "document-processor"
  lambda_runtime       = "python3.11"
  lambda_memory_size   = 1024
  lambda_timeout       = 300
  
  # ... other configuration
}
```

## Testing

To test the Lambda function locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/
```

## Monitoring

- **CloudWatch Logs**: `/aws/lambda/document-processor`
- **X-Ray Tracing**: Enabled for distributed tracing
- **Metrics**: Lambda invocations, errors, duration
- **Dead Letter Queue**: Failed invocations sent to SQS DLQ

## Error Handling

The function implements comprehensive error handling:

1. **Record-Level Errors**: Individual S3 records that fail are logged and reported
2. **Dead Letter Queue**: Failed Lambda invocations are sent to SQS DLQ
3. **Retry Logic**: Bedrock ingestion failures trigger exponential backoff retry
4. **CloudWatch Alarms**: Configured for high error rates

## Performance Considerations

- **Memory**: 1024 MB minimum for document processing
- **Timeout**: 300 seconds (5 minutes) for complex documents
- **VPC Configuration**: Deployed in private subnets for security
- **Concurrent Executions**: Configurable based on workload

## Future Enhancements

- [ ] Support for additional document formats (DOCX, PPTX)
- [ ] Advanced text extraction from diagrams using OCR
- [ ] Custom chunking strategies via configuration
- [ ] Batch processing for multiple documents
- [ ] Metadata enrichment and tagging
