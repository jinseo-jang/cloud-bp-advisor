import os
import json
import time
import zipfile
import datetime
from google.cloud import pubsub_v1
from google.api_core.exceptions import DeadlineExceeded, RetryError
import requests.exceptions

import logger
from terraform_executor import run_terraform
# ...

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or os.environ.get("GCP_PROJECT_ID") or ""
SUBSCRIPTION_NAME = "sandbox-job-sub-v2"

# GCS, BigQuery, and Vertex Search ingestion removed for performance.
def process_message(message):
    print(f"Received message ID: {message.message_id}", flush=True)
    
    try:
        data = json.loads(message.data.decode("utf-8"))
        job_id = data.get("job_id")
        tf_code = data.get("terraform_code")
        cloud = data.get("cloud", "AWS")
        is_final_retry = data.get("is_final_retry", False)
        
        if not job_id or not tf_code:
            message.ack()
            return
            
        logger.stream_log(job_id, "[Sandbox Worker] Job pulled from Pub/Sub. Starting execution...")
        
        # 1. Run Terraform Validation
        status, feedback = run_terraform(job_id, tf_code, is_final_retry)
        
        if status == "passed":
            logger.update_status(job_id, "success", "")
        else:
            logger.update_status(job_id, "failed", feedback)
            
    except Exception as e:
        print(f"Error processing message: {e}", flush=True)
    finally:
        pass

def start_worker():
    # Force REST transport to bypass gRPC issues in gVisor
    subscriber = pubsub_v1.SubscriberClient(transport="rest")
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_NAME)
    
    print(f"[{datetime.datetime.now()}] Listening for messages via REST (Synchronous) on {subscription_path}...", flush=True)

    # Heartbeat thread to show the worker is still alive
    def heartbeat():
        while True:
            print(f"[{datetime.datetime.now()}] Heartbeat: Sandbox Worker (REST) is alive and listening...", flush=True)
            time.sleep(30)
    
    import threading
    h_thread = threading.Thread(target=heartbeat, daemon=True)
    h_thread.start()

    while True:
        try:
            # REST transport requires manual pulling (Sync Pull)
            response = subscriber.pull(
                request={"subscription": subscription_path, "max_messages": 1},
                timeout=15.0
            )
            for msg in response.received_messages:
                print(f"[{datetime.datetime.now()}] !!! RECEIVED MESSAGE ID: {msg.message.message_id} !!!", flush=True)
                
                # Acknowledge immediately before long processing
                subscriber.acknowledge(
                    request={
                        "subscription": subscription_path,
                        "ack_ids": [msg.ack_id]
                    }
                )
                
                try:
                    process_message(msg.message)
                except Exception as e:
                    print(f"Error processing message: {e}", flush=True)

        except Exception as e:
            err_str = str(e)
            # Silence all expected timeouts
            if any(x in err_str for x in ["timed out", "DeadlineExceeded", "RetryError"]):
                continue
            
            if isinstance(e, (DeadlineExceeded, RetryError, requests.exceptions.Timeout)):
                continue

            print(f"[{datetime.datetime.now()}] Pull error: {err_str}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    start_worker()
