import datetime
import os
import requests
import google.auth
import google.auth.transport.requests

project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or os.environ.get("GCP_PROJECT_ID") or "duper-project-1"
database_id = "cloud-bp-db"

_credentials = None

def get_token():
    """Gets a fresh OAuth2 token for REST API calls."""
    global _credentials
    if _credentials is None:
        _credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    
    if not _credentials.valid:
        auth_req = google.auth.transport.requests.Request()
        _credentials.refresh(auth_req)
    return _credentials.token

def firestore_patch(session_id: str, data: dict):
    """Performs a direct documents.patch call via REST API."""
    token = get_token()
    url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/{database_id}/documents/sandbox_logs/{session_id}"
    
    # Construct fields for the REST API (minimal implementation for our specific needs)
    fields = {}
    update_mask_query = []
    
    if "logs" in data:
        # We handle ArrayUnion by getting current and appending, or just sending the whole list
        # For simplicity in REST, we'll send a full update if we can, or just append.
        # However, REST patch is tricky with arrays. 
        # For this debug fix, we will just use a simple 'set' behavior for status and a list for logs.
        # Let's simplify and just use logs as a string or list.
        pass

    # A more robust REST implementation:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # We'll use the 'mask' to update specific fields
    payload = {"fields": {}}
    mask_params = []
    
    if "status" in data:
        payload["fields"]["status"] = {"stringValue": data["status"]}
        mask_params.append("updateMask.fieldPaths=status")
    if "error_details" in data:
        payload["fields"]["error_details"] = {"stringValue": data["error_details"]}
        mask_params.append("updateMask.fieldPaths=error_details")
    if "logs" in data:
        # Array support in REST is heavy. Let's just send the most recent message for now
        # OR better: use transform for ArrayUnion.
        # But to keep it 100% reliable and simple:
        pass

    query_string = "&".join(mask_params)
    target_url = f"{url}?{query_string}"
    
    try:
        resp = requests.patch(target_url, headers=headers, json=payload, timeout=10)
        if resp.status_code not in [200, 201]:
            print(f"Firestore REST error ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Firestore REST exception: {e}")

def stream_log(session_id: str, message: str):
    """Writes log entry using Firestore REST API 'transform' (ArrayUnion equivalent)."""
    print(f"[{session_id}] {message}", flush=True)
    token = get_token()
    
    # URL must be at the database level for a commit write
    url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/{database_id}/documents:commit"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Construction according to Firestore REST API Spec
    payload = {
        "writes": [
            {
                "transform": {
                    "document": f"projects/{project_id}/databases/{database_id}/documents/sandbox_logs/{session_id}",
                    "fieldTransforms": [
                        {
                            "fieldPath": "logs",
                            "appendMissingElements": {
                                "values": [{"stringValue": message}]
                            }
                        }
                    ]
                }
            }
        ]
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
        if resp.status_code != 200:
            print(f"Firestore Log error ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"Firestore Log exception: {e}")

def update_status(session_id: str, status: str, error_details: str = ""):
    """Updates status via direct REST API."""
    print(f"[{session_id}] Setting status: {status}", flush=True)
    firestore_patch(session_id, {"status": status, "error_details": error_details})
