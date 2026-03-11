import json
import asyncio
import os
from google.cloud import pubsub_v1
from google.cloud import firestore
from src.config import GCP_PROJECT_ID

project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID)

def get_publisher():
    try:
        return pubsub_v1.PublisherClient()
    except Exception as e:
        print(f"[PubSub] Error initializing publisher: {e}")
        return None

def get_firestore_client():
    try:
        return firestore.AsyncClient(project=project_id, database="cloud-bp-db")
    except Exception as e:
        print(f"[Firestore] Error initializing client: {e}")
        return None

async def publish_job_and_stream_logs(job_id: str, tf_code: str, cloud: str, is_final_retry: bool = False):
    """
    Publishes a job to Pub/Sub and polls Firestore for real-time logs to yield as SSE.
    Returns (status, feedback) where status is 'success' or 'failed'.
    """
    publisher = get_publisher()
    db = get_firestore_client()
    
    if not publisher or not db:
        yield "data: [Error] PubSub or Firestore client initialization failed.\n\n"
        yield "data: [END]\n\n"
        yield {"status": "failed", "feedback": "GCP Clients not initialized."}
        return

    topic_path = publisher.topic_path(project_id, "sandbox-job-topic")
    print(f"[Backend] Publishing to topic: {topic_path}", flush=True)
    msg_data = json.dumps({
        "job_id": job_id,
        "terraform_code": tf_code,
        "cloud": cloud,
        "is_final_retry": is_final_retry
    }).encode("utf-8")
    
    try:
        publisher.publish(topic_path, msg_data).result()
        yield f"data: [Backend] Job {job_id} published to Pub/Sub.\n\n"
    except Exception as e:
        yield f"data: [Error] Failed to publish job: {e}\n\n"
        yield {"status": "failed", "feedback": str(e)}
        return
    
    doc_ref = db.collection("sandbox_logs").document(job_id)
    
    # Poll Firestore document for new logs array items
    last_idx = 0
    final_status = None
    feedback = ""
    
    # We will poll for up to 5 minutes
    timeout_loops = 600
    while timeout_loops > 0:
        try:
            doc = await doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                logs = data.get("logs", [])
                
                # Yield new logs
                for i in range(last_idx, len(logs)):
                    line = logs[i]
                    if line.strip():
                        yield f"data: {line}\n\n"
                last_idx = len(logs)
                
                status = data.get("status")
                if status in ["success", "failed"]:
                    final_status = status
                    feedback = data.get("error_details", "No specific error provided.")
                    break
        except Exception as e:
            yield f"data: [Firestore] Error reading document: {e}\n\n"
            
        await asyncio.sleep(0.5)
        timeout_loops -= 1

    if final_status is None:
        final_status = "failed"
        feedback = "Timeout waiting for sandbox worker to complete the job."
        yield f"data: [Error] {feedback}\n\n"

    yield {"status": final_status, "feedback": feedback}
