
import asyncio
import sys
import os
import json
from dotenv import load_dotenv
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock Phase 1 Agents
async def mock_orchestrator_node(state):
    print("   [Mock] Orchestrator running...")
    return {"user_requirement": state["user_requirement"]}

async def mock_aws_architect_node(state):
    print("   [Mock] AWS Architect running...")
    return {"architecture_proposals": {"AWS": {"description": "Mocked AWS Arch", "services": ["s3"]}}}

async def mock_gcp_architect_node(state):
    print("   [Mock] GCP Architect running...")
    return {"architecture_proposals": {"GCP": {"description": "Mocked GCP Arch", "services": ["gcs"]}}}

async def mock_merge_architectures_node(state):
    print("   [Mock] Merging Architectures...")
    return {"architecture_proposals": {"AWS": {"description": "Mocked AWS Arch"}, "GCP": {"description": "Mocked GCP Arch"}}}

# Patch modules
import src.agents.e2e_workflow
src.agents.e2e_workflow.orchestrator_node = mock_orchestrator_node
src.agents.e2e_workflow.aws_architect_node = mock_aws_architect_node
src.agents.e2e_workflow.gcp_architect_node = mock_gcp_architect_node
src.agents.e2e_workflow.merge_architectures_node = mock_merge_architectures_node

# Re-compile graph
from src.state import GraphState
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

def rebuild_graph_with_mocks():
    from src.agents.e2e_workflow import (
        orchestrator_node, aws_architect_node, gcp_architect_node, 
        merge_architectures_node, feedback_review_node, tf_coder_node, 
        qa_validator_node, approval_node, tf_runner_node, 
        route_after_feedback, check_qa_status, check_sandbox_status,
        GraphState
    )
    
    workflow = StateGraph(GraphState)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("aws_architect", aws_architect_node)
    workflow.add_node("gcp_architect", gcp_architect_node)
    workflow.add_node("merge_architectures", merge_architectures_node)
    workflow.add_node("feedback_review", feedback_review_node)
    workflow.add_node("tf_coder", tf_coder_node)
    workflow.add_node("qa_validator", qa_validator_node)
    workflow.add_node("approval_node", approval_node)
    workflow.add_node("tf_runner", tf_runner_node)
    
    workflow.set_entry_point("orchestrator")
    workflow.add_edge("orchestrator", "aws_architect")
    workflow.add_edge("orchestrator", "gcp_architect")
    workflow.add_edge("aws_architect", "merge_architectures")
    workflow.add_edge("gcp_architect", "merge_architectures")
    workflow.add_edge("merge_architectures", "feedback_review")
    
    workflow.add_conditional_edges("feedback_review", route_after_feedback, ["aws_architect", "gcp_architect", "tf_coder"])
    workflow.add_edge("tf_coder", "qa_validator")
    workflow.add_conditional_edges("qa_validator", check_qa_status, {"retry": "tf_coder", "pass": "approval_node"})
    workflow.add_edge("approval_node", "tf_runner")
    workflow.add_conditional_edges("tf_runner", check_sandbox_status, {"retry": "tf_coder", "pass": END})
    
    memory = MemorySaver()
    # Interrupt before approval to stop after QA
    return workflow.compile(checkpointer=memory, interrupt_before=["feedback_review", "approval_node"])

load_dotenv()

async def simulate_ui_render():
    print("🚀 [TEST START] Simulating Streamlit UI Event Loop (Force Phase 2)...")
    
    test_graph = rebuild_graph_with_mocks()
    session_state = {"messages": []}
    
    req = "Create a simple AWS S3 bucket with public read access policy."
    initial_state = {"user_requirement": req}
    config = {"configurable": {"thread_id": "test-thread-mock-2"}}
    
    node_retry_counts = {}
    
    print("\n🔄 [Graph Execution] Phase 1: Planning (Mocked)")
    try:
        async for event in test_graph.astream_events(initial_state, config, version="v2"):
            if event["event"] == "on_chain_end" and event.get("name") in ["orchestrator", "aws_architect", "gcp_architect", "merge_architectures"]:
                print(f"✅ [Phase 1] Finished Node: {event.get('name')}")
    except Exception as e:
        print(f"❌ Phase 1 Error: {e}")

    print("\n✋ [Human-in-the-Loop] Simulating Selection (NO extra feedback to skip re-architecting)...")
    # Setting user_feedback="" ensures we go to tf_coder, NOT back to architects
    test_graph.update_state(config, {"selected_cloud": "AWS", "user_feedback": ""}, as_node="feedback_review")
    
    print("\n🔄 [Graph Execution] Phase 2: Coding & QA (Connecting to Real LLM via .env)")
    
    try:
        async for event in test_graph.astream_events(None, config, version="v2"):
            event_type = event["event"]
            node_name = event.get("name", "")
            tags = event.get("tags", [])
            
            # Print EVERYTHING to debug
            if event_type == "on_chat_model_start":
                print(f"\n   [LLM Start] Node: {node_name} | Metadata: {event.get('metadata', {})}")
            
            if event_type == "on_chain_start" and node_name in ["tf_coder", "qa_validator", "approval_node"]:
                print(f"\n   [Node Start] {node_name}")
                
            if event_type == "on_chat_model_stream":
                print(".", end="", flush=True)

            if event_type == "on_chain_end" and node_name in ["tf_coder", "qa_validator", "approval_node"]:
                node_retry_counts[node_name] = node_retry_counts.get(node_name, 0) + 1
                retry_count = node_retry_counts[node_name]
                print(f"\n✅ [Phase 2] Finished Node: {node_name} (Retry: {retry_count})")
                
                if node_name == "qa_validator":
                    # Deep inspect output
                    output = event.get('data', {}).get('output', {})
                    if output:
                        final_text = output.get('qa_final_text', '')
                        if "FAIL_SECURITY" in final_text:
                            print(f"     🚨 FAIL_SECURITY detected. (System should retry)")
                        elif "PASS_SECURITY" in final_text:
                            print(f"     🟢 PASS_SECURITY detected.")
                        else:
                            print(f"     ❓ Unknown QA Result: {final_text[:50]}...")
                            
                session_state["messages"].append({"node": node_name, "retry": retry_count})

    except Exception as e:
        print(f"\n❌ Phase 2 Error: {e}")
            
    print("\n🏁 [TEST END] Summary:")
    qa_runs = [m for m in session_state["messages"] if m["node"] == "qa_validator"]
    print(f"   Total QA Runs: {len(qa_runs)}")
    
    if len(qa_runs) >= 1:
        print("✅ TEST PASSED: Phase 2 executed.")
    else:
        print("❌ TEST FAILED: Phase 2 did not complete QA.")

if __name__ == "__main__":
    asyncio.run(simulate_ui_render())
