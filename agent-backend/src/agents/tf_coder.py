from src.config import GEMINI_PRO_MODEL, GCP_PROJECT_ID
import json
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from src.state import GraphState
from src.agents.prompts import TF_CODER_SYSTEM_PROMPT
from src.agents.tools import context7_mcp, infracost_estimate

def tf_coder_node(state: GraphState) -> dict:
    cloud = state.get("selected_cloud", "AWS")
    print(f"[TF Coder] Generating HCL for {cloud}")
    
    feedback = state.get("qa_feedback", [])
    feedback_str = f"QA Feedback to incorporate:\n{feedback[-1]}" if feedback else "No feedback. Initial clean run."
    
    llm = ChatGoogleGenerativeAI(model=GEMINI_PRO_MODEL, temperature=0.1, project=os.environ.get("GOOGLE_CLOUD_PROJECT", GCP_PROJECT_ID), location="global", client_options={"api_endpoint": "https://aiplatform.googleapis.com"})
    llm.client._api_client._http_options.api_version = "v1"
    tools = [context7_mcp]
    
    agent_executor = create_react_agent(llm, tools, prompt=TF_CODER_SYSTEM_PROMPT)
    proposals = state.get("architecture_proposals", {})
    selected_arch = proposals.get(cloud, {})
    
    prompt = (
        f"Target Cloud: {cloud}\\n"
        f"Architecture Proposal: {json.dumps(selected_arch)}\\n"
        f"{feedback_str}\\n\\n"
        "Return the response strictly as a JSON object with two keys: "
        "'terraform_code' (string containing the raw HCL) and 'terraform_metadata' (dictionary containing the cost and other tags)."
    )
    
    try:
        result = agent_executor.invoke({"messages": [("user", prompt)]})
        final_text = result["messages"][-1].content
        if isinstance(final_text, list):
            final_text = "".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in final_text)
        
        if "```json" in final_text:
            json_str = final_text.split("```json")[1].split("```")[0].strip()
        else:
            json_str = final_text.strip("` \n")
            if json_str.startswith("json"): json_str = json_str[4:].strip()
            
        parsed = json.loads(json_str)
        hcl_code = parsed.get("terraform_code", "")
        metadata = parsed.get("terraform_metadata", {})
    except Exception as e:
        print(f"[TF Coder] LLM evaluation error: {e}. Falling back to default.")
        hcl_code = f"// Mocked Terraform for {cloud}\nresource \"example\" \"main\" {{}}"
        metadata = {"cloud": cloud, "tags": ["fallback"]}

    return {
        "terraform_code": hcl_code, 
        "terraform_metadata": metadata,
        "current_step": "tf_coder_done"
    }
