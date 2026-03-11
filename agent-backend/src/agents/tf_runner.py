import json
import asyncio
import uuid
from src.state import GraphState
from src.agents.tf_coder import tf_coder_node
from src.agents.qa_validator import qa_validator_node
from src.agents.pubsub_firestore import publish_job_and_stream_logs

async def execute_and_correct_loop(state: GraphState, max_retries=3):
    """
    Executes Terraform via Pub/Sub and reads logs via Firestore SSE. 
    If it fails, loops back to tf_coder_node -> qa_validator_node up to max_retries.
    Yields chunks of SSE formatted strings.
    """
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    retries = 0
    cloud = state.get("selected_cloud", "AWS")
    
    while retries < max_retries:
        yield f"data: [Sandbox] Attempt {retries + 1}/{max_retries} to provision...\n\n"
        
        tf_code = state.get("terraform_code", "")
        if not tf_code:
            yield "data: [Sandbox] Error: No Terraform code found in state.\n\n"
            break
            
        yield f"data: [Sandbox] Initializing Async Terraform Execution via Pub/Sub (Job: {job_id})...\n\n"
        
        status, feedback = None, None
        
        # Async stream logs from pubsub_firestore
        async for chunk in publish_job_and_stream_logs(job_id, tf_code, cloud):
            if isinstance(chunk, dict) and "status" in chunk:
                status = chunk["status"]
                feedback = chunk["feedback"]
            else:
                yield chunk
                
        if status == "success":
            yield "data: [Sandbox] Success! Infrastructure provisioned.\n\n"
            yield "data: [END]\n\n"
            break
        else:
            yield f"data: [Sandbox] Apply Failed. Extracting error logs...\n\n"
            yield f"data: {json.dumps({'type': 'execute_failed', 'feedback': str(feedback)})}\n\n"
            yield "data: [END]\n\n"
            break
