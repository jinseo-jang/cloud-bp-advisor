import json
import os

def process_and_upload_artifacts(session_id: str, tf_code: str, metadata: dict):
    """
    Packages the validated TF code and Markdown docs into a ZIP.
    Uploads ZIP to GCS.
    Indexes the chunks with JSON metadata into Vertex AI Search Datastore.
    """
    # 1. Package Artifacts
    artifact_path = f"/tmp/{session_id}/architecture_pack.zip"
    print(f"Packaging artifacts into {artifact_path}...")
    
    # 2. Upload to GCS
    bucket_name = os.getenv("GCS_BUCKET", "cba-artifacts-bucket")
    print(f"Uploading {artifact_path} to gs://{bucket_name}/{session_id}/")
    
    # 3. Vertex AI Search Metadata Ingestion
    datastore = os.getenv("DATASTORE_ID", "architecture-patterns-ds")
    
    json_metadata = json.dumps({
        "id": f"arch-{session_id}",
        "cloud_provider": metadata.get("cloud", "AWS"),
        "cost_tier": metadata.get("cost_tier", "medium"),
        "tags": metadata.get("tags", []),
        "content": tf_code  # Assisting RAG capabilities
    })
    
    # DiscoveryEngine API call goes here
    print(f"Ingesting into Vertex AI Datastore: {datastore} -> {json_metadata[:50]}...")
