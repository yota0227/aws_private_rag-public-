# OpenSearch Serverless Configuration for Bedrock RAG
# Creates OpenSearch Serverless collection with vector search capabilities

# Data source for current AWS account and region
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# OpenSearch Serverless Encryption Policy
resource "aws_opensearchserverless_security_policy" "encryption" {
  name        = "${var.opensearch_collection_name}-encryption"
  type        = "encryption"
  description = "Encryption policy for ${var.opensearch_collection_name}"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource = [
          "collection/${var.opensearch_collection_name}"
        ]
      }
    ]
    AWSOwnedKey = false
    KmsARN      = var.kms_key_arn
  })
}

# OpenSearch Serverless Network Policy
resource "aws_opensearchserverless_security_policy" "network" {
  name        = "${var.opensearch_collection_name}-network"
  type        = "network"
  description = "Network policy for ${var.opensearch_collection_name}"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/${var.opensearch_collection_name}"
          ]
        },
        {
          ResourceType = "dashboard"
          Resource = [
            "collection/${var.opensearch_collection_name}"
          ]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

# OpenSearch Serverless Collection
resource "aws_opensearchserverless_collection" "main" {
  name        = var.opensearch_collection_name
  type        = "VECTORSEARCH"
  description = "Vector search collection for Bedrock Knowledge Base"

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network
  ]

  tags = merge(
    var.tags,
    {
      Name = var.opensearch_collection_name
      Type = "VectorSearch"
    }
  )
}

# OpenSearch Serverless Data Access Policy
resource "aws_opensearchserverless_access_policy" "data_access" {
  name        = "${var.opensearch_collection_name}-data-access"
  type        = "data"
  description = "Data access policy for ${var.opensearch_collection_name}"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/${var.opensearch_collection_name}"
          ]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems"
          ]
        },
        {
          ResourceType = "index"
          Resource = [
            "index/${var.opensearch_collection_name}/*"
          ]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:UpdateIndex",
            "aoss:DeleteIndex"
          ]
        }
      ]
      Principal = distinct([
        var.bedrock_execution_role_arn,
        var.opensearch_access_role_arn
      ])
    }
  ])

  depends_on = [aws_opensearchserverless_collection.main]
}

# Wait for collection to be active before creating index
resource "time_sleep" "wait_for_collection" {
  depends_on = [
    aws_opensearchserverless_collection.main,
    aws_opensearchserverless_access_policy.data_access
  ]

  create_duration = "60s"
}

# Note: Vector index creation requires manual setup or external script
# The index must be created before the Bedrock Knowledge Base can use it
# Use the index mapping file created below as a reference

# Create OpenSearch Vector Index using local-exec provisioner
# This creates the index with proper vector field configuration for Bedrock
# NOTE: This requires curl and AWS CLI v2 with appropriate IAM permissions

resource "null_resource" "create_vector_index" {
  depends_on = [time_sleep.wait_for_collection]

  triggers = {
    collection_endpoint = aws_opensearchserverless_collection.main.collection_endpoint
    index_name          = var.opensearch_index_name
    vector_dimension    = var.vector_dimension
  }

  provisioner "local-exec" {
    command = <<-EOT
      # Create index mapping JSON
      cat > /tmp/opensearch_index_mapping.json <<'EOF'
      {
        "settings": {
          "index": {
            "knn": true,
            "knn.algo_param.ef_search": 512
          }
        },
        "mappings": {
          "properties": {
            "bedrock-knowledge-base-default-vector": {
              "type": "knn_vector",
              "dimension": ${var.vector_dimension},
              "method": {
                "name": "hnsw",
                "engine": "faiss",
                "parameters": {
                  "ef_construction": 512,
                  "m": 16
                }
              }
            },
            "AMAZON_BEDROCK_TEXT_CHUNK": {
              "type": "text"
            },
            "AMAZON_BEDROCK_METADATA": {
              "type": "text",
              "index": false
            }
          }
        }
      }
      EOF

      # Create the index using curl with AWS SigV4 signing
      # This requires awscurl or similar tool
      echo "Creating OpenSearch index ${var.opensearch_index_name}..."
      
      # Using Python with boto3 and requests-aws4auth for SigV4 signing
      python3 -c "
import json
import boto3
from requests_aws4auth import AWS4Auth
import requests

region = 'us-east-1'
service = 'aoss'
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)

endpoint = '${aws_opensearchserverless_collection.main.collection_endpoint}'
index_name = '${var.opensearch_index_name}'
url = f'{endpoint}/{index_name}'

with open('/tmp/opensearch_index_mapping.json', 'r') as f:
    index_body = json.load(f)

try:
    response = requests.put(url, auth=awsauth, json=index_body, headers={'Content-Type': 'application/json'})
    print(f'Status: {response.status_code}')
    print(f'Response: {response.text}')
    if response.status_code in [200, 201]:
        print('Index created successfully')
    elif response.status_code == 400 and 'resource_already_exists_exception' in response.text:
        print('Index already exists')
    else:
        print('Failed to create index')
except Exception as e:
    print(f'Error: {e}')
    print('Index creation failed - you may need to create it manually')
" || echo "Python script failed - index may need to be created manually"

      # Clean up
      rm -f /tmp/opensearch_index_mapping.json
    EOT
  }

  # Destroy provisioner to clean up index (optional)
  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      echo "Note: OpenSearch index cleanup should be done manually if needed"
    EOT
  }
}

# Alternative: Create index mapping file for manual creation
resource "local_file" "index_mapping" {
  filename = "${path.module}/opensearch_index_mapping.json"
  content = jsonencode({
    settings = {
      index = {
        knn                      = true
        "knn.algo_param.ef_search" = 512
      }
    }
    mappings = {
      properties = {
        "bedrock-knowledge-base-default-vector" = {
          type      = "knn_vector"
          dimension = var.vector_dimension
          method = {
            name   = "hnsw"
            engine = "faiss"
            parameters = {
              ef_construction = 512
              m               = 16
            }
          }
        }
        AMAZON_BEDROCK_TEXT_CHUNK = {
          type = "text"
        }
        AMAZON_BEDROCK_METADATA = {
          type  = "text"
          index = false
        }
      }
    }
  })
}


# CloudWatch Log Group for OpenSearch
resource "aws_cloudwatch_log_group" "opensearch" {
  name              = "/aws/opensearch/${var.opensearch_collection_name}"
  retention_in_days = 7

  tags = merge(
    var.tags,
    {
      Name = "${var.opensearch_collection_name}-logs"
    }
  )
}
