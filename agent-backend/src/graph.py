from langgraph.graph import StateGraph, END
from .state import GraphState
from .agents import (
    orchestrator_node,
    aws_architect_node,
    gcp_architect_node,
    tf_coder_node,
    qa_validator_node
)

def route_after_qa(state: GraphState) -> str:
    """Conditional Edge: Loop back to TF Coder if QA fails, else END."""
    if state.get("sandbox_status") == "failed":
        return "tf_coder"
    return END

def build_graph():
    """
    Builds the state machine linking the 5 core agents based on the PRD 6-step workflow.
    """
    workflow = StateGraph(GraphState)
    
    # 1. Add Nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("aws_architect", aws_architect_node)
    workflow.add_node("gcp_architect", gcp_architect_node)
    workflow.add_node("tf_coder", tf_coder_node)
    workflow.add_node("qa_validator", qa_validator_node)
    
    # 2. Add Edges 
    workflow.set_entry_point("orchestrator")
    
    # Phase 1: Deep Search & Parallel Architecture Generation
    workflow.add_edge("orchestrator", "aws_architect")
    workflow.add_edge("orchestrator", "gcp_architect")
    
    # End of Phase 1 (Wait for User Selection)
    workflow.add_edge("aws_architect", END)
    workflow.add_edge("gcp_architect", END)
    
    # Phase 2: Implementation & Self-Healing QA
    workflow.add_edge("tf_coder", "qa_validator")
    
    # Conditional Loop for QA Feedback
    workflow.add_conditional_edges(
        "qa_validator",
        route_after_qa,
        {
            "tf_coder": "tf_coder",
            END: END
        }
    )
    
    return workflow.compile()
