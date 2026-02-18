#!/usr/bin/env python3
"""
Create OpenSearch Serverless Index for Bedrock Knowledge Base
This script creates a vector index in OpenSearch Serverless collection
with the proper configuration for Bedrock Knowledge Base.
"""

import json
import sys
import boto3
from requests_aws4auth import AWS4Auth
import requests

def create_opensearch_index(collection_endpoint, index_name, vector_dimension=1536):
    """
    Create an OpenSearch index with vector search capabilities.
    
    Args:
        collection_endpoint: OpenSearch Serverless collection endpoint
        index_name: Name of the index to create
        vector_dimension: Dimension of the vector embeddings (default: 1536 for Titan)
    """
    region = 'us-east-1'
    service = 'aoss'
    
    # Get AWS credentials
    session = boto3.Session()
    credentials = session.get_credentials()
    
    # Create AWS4Auth for SigV4 signing
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        service,
        session_token=credentials.token
    )
    
    # Index mapping configuration
    index_body = {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 512
            }
        },
        "mappings": {
            "properties": {
                "bedrock-knowledge-base-default-vector": {
                    "type": "knn_vector",
                    "dimension": vector_dimension,
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
                    "index": False
                }
            }
        }
    }
    
    # Create the index
    url = f"{collection_endpoint}/{index_name}"
    
    try:
        print(f"Creating index '{index_name}' at {collection_endpoint}...")
        response = requests.put(
            url,
            auth=awsauth,
            json=index_body,
            headers={'Content-Type': 'application/json'}
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code in [200, 201]:
            print(f"✅ Index '{index_name}' created successfully!")
            return True
        elif response.status_code == 400 and 'resource_already_exists_exception' in response.text:
            print(f"ℹ️  Index '{index_name}' already exists")
            return True
        else:
            print(f"❌ Failed to create index: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error creating index: {e}")
        return False

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 create-opensearch-index.py <collection_endpoint> <index_name> [vector_dimension]")
        print("Example: python3 create-opensearch-index.py https://xxx.us-east-1.aoss.amazonaws.com bedrock-knowledge-base-index 1536")
        sys.exit(1)
    
    collection_endpoint = sys.argv[1]
    index_name = sys.argv[2]
    vector_dimension = int(sys.argv[3]) if len(sys.argv) > 3 else 1536
    
    success = create_opensearch_index(collection_endpoint, index_name, vector_dimension)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
