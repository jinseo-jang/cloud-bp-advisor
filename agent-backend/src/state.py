from typing import Annotated, Dict, Any, List, Optional
from typing_extensions import TypedDict

def append_to_list(left: list, right: list) -> list:
    """Reducer function to append feedback elements."""
    if right is None:
        return left
    return left + right

class GraphState(TypedDict):
    """
    Enterprise Cloud Architecture Generation - LangGraph State
    This state object is passed and modified among all 5 agents.
    """
    user_requirement: str                       # User's natural language request
    selected_cloud: Optional[str]               # 'AWS' or 'GCP' (set in Phase 2)
    
    # Phase 1: Architecture Proposals
    architecture_proposals: Dict[str, Any]      # e.g., {'AWS': {'diagram': '...', 'cost': '...'}, 'GCP': {...}}
    
    # Phase 2: Implementation & QA
    terraform_code: Optional[str]               # Generated HCL code
    terraform_metadata: Dict[str, Any]          # JSON metadata for Vertex AI RAG Ingestion
    qa_feedback: Annotated[List[str], append_to_list] # Feedback / Error logs from Sandbox
    
    # State tracking
    sandbox_status: str                         # 'pending', 'passed', 'failed'
    current_step: str                           # Current node or logical step
