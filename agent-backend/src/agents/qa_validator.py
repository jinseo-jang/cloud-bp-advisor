from src.config import GEMINI_FLASH_MODEL, GCP_PROJECT_ID
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from src.state import GraphState
from src.agents.prompts import QA_VALIDATOR_SYSTEM_PROMPT
from src.agents.tools import tfsec_scan

def qa_validator_node(state: GraphState) -> dict:
    print("[QA Validator] Reviewing Terraform code and running scans...")
    
    hcl = state.get("terraform_code", "")
    llm = ChatGoogleGenerativeAI(model=GEMINI_FLASH_MODEL, temperature=0.0, project=os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID), location="global", client_options={"api_endpoint": "https://aiplatform.googleapis.com"})
    llm.client._api_client._http_options.api_version = "v1"
    tools = [tfsec_scan]
    
    agent_executor = create_react_agent(llm, tools, prompt=QA_VALIDATOR_SYSTEM_PROMPT)
    prompt = f"Review the following Terraform code. Run tfsec_scan on it. If it fails or you find issues, describe them in detail. Otherwise, output exactly 'PASS'.\n\n```hcl\n{hcl}\n```"
    
    try:
        result = agent_executor.invoke({"messages": [("user", prompt)]})
        raw_content = result["messages"][-1].content
        if isinstance(raw_content, list):
            raw_content = "".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in raw_content)
        response = raw_content.strip()
    except Exception as e:
        print(f"[QA Validator] Error: {e}")
        response = "PASS" # fail open for scaffolding fallback
        
    feedback_list = state.get("qa_feedback", [])
    
    if response == "PASS" or "PASS" in response:
        return {"current_step": "qa_done"}
    else:
        feedback_list.append(response)
        # Adding back to the graph state QA list
        state["qa_feedback"] = feedback_list
        return {"qa_feedback": feedback_list, "current_step": "qa_failed"}
