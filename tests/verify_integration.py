import os
import sys
import json
import time
import asyncio
from typing import List, Any

# Ensure we can import from src if needed, but we'll use direct clients for robustness
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from google.cloud import firestore
    from google.cloud import pubsub_v1
    from google.cloud import storage
except ImportError:
    print("Error: Missing google-cloud dependencies. Please run in the correct environment.")
    sys.exit(1)

PROJECT_ID = "duper-project-1"
REGION = "asia-northeast3"
DATABASE_NAME = "cloud-bp-db"
BUCKET_NAME = f"{PROJECT_ID}-cba-artifacts"
TOPIC_NAME = "sandbox-job-topic"
SUBSCRIPTION_NAME = "sandbox-job-sub-v2"

os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID

def check_firestore_empty():
    print(f"\n--- Checking Firestore Database: {DATABASE_NAME} ---")
    db = firestore.Client(database=DATABASE_NAME)
    
    collections = ["chat_sessions", "sandbox_logs"]
    for col in collections:
        docs = list(db.collection(col).limit(10).get())
        if docs:
            print(f"  [FAIL] Collection '{col}' is NOT empty. Found {len(docs)} documents.")
            return False
        else:
            print(f"  [PASS] Collection '{col}' is empty.")
    return True

def check_pubsub_active():
    print("\n--- Checking Pub/Sub Status ---")
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_NAME)
    
    try:
        sub = subscriber.get_subscription(request={"subscription": subscription_path})
        print(f"  [PASS] Subscription '{SUBSCRIPTION_NAME}' is ACTIVE.")
        return True
    except Exception as e:
        print(f"  [FAIL] Could not access subscription '{SUBSCRIPTION_NAME}': {e}")
        return False

def check_gcs_clean():
    print(f"\n--- Checking GCS Bucket: {BUCKET_NAME} ---")
    storage_client = storage.Client()
    try:
        bucket = storage_client.get_bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs(max_results=10))
        if blobs:
            print(f"  [FAIL] Bucket '{BUCKET_NAME}' is NOT empty. Found {len(blobs)} blobs.")
            return False
        else:
            print(f"  [PASS] Bucket '{BUCKET_NAME}' is empty.")
        return True
    except Exception as e:
        print(f"  [FAIL] Could not access bucket '{BUCKET_NAME}': {e}")
        return False

def verify_clean_state():
    print("========================================")
    print("  VERIFYING CLEAN INFRASTRUCTURE STATE  ")
    print("========================================")
    
    results = [
        check_firestore_empty(),
        check_pubsub_active(),
        check_gcs_clean()
    ]
    
    if all(results):
        print("\n[SUCCESS] All checks passed. Environment is CLEAN and READY.")
        return True
    else:
        print("\n[FAILURE] Some clean state checks failed.")
        return False

if __name__ == "__main__":
    # If 'clean' argument is passed, verify empty state
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        if not verify_clean_state():
            sys.exit(1)
    else:
        print("Usage: python3 tests/verify_integration.py clean")
        sys.exit(1)
