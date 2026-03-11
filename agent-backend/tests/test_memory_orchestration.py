from src.config import GEMINI_MODEL
import pytest
import os
import json
from unittest.mock import patch, MagicMock
from src.memory import extract_and_store_facts, MemoryBank

@pytest.mark.asyncio
@patch('src.memory.ChatGoogleGenerativeAI')
@patch('src.memory.MemoryBank')
async def test_memory_extraction(MockMemoryBank, MockChatLLM):
    # Setup mocks
    mock_llm_instance = MagicMock()
    MockChatLLM.return_value = mock_llm_instance
    mock_response = MagicMock()
    mock_response.content = "User wanted a secure AWS 3-tier app. Outcome: Failed due to VPC limit."
    
    from unittest.mock import AsyncMock
    mock_llm_instance.ainvoke = AsyncMock(return_value=mock_response)
    
    mock_bank_instance = MagicMock()
    MockMemoryBank.return_value = mock_bank_instance
    
    # Simulate a giant state payload
    giant_tf = "resource 'aws_vpc' 'main' { cidr_block = '10.0.0.0/16' }\n" * 1000
    giant_logs = "Error: Quota exceeded for AWS VPC. " * 500
    
    mock_state = {
        "user_requirement": "I need a highly secure AWS application.",
        "selected_cloud": "aws",
        "architecture_docs": "Standard 3-tier AWS architecture...",
        "terraform_code": giant_tf,
        "qa_feedback": "Looks good but need to check quotas.",
        "sandbox_logs": giant_logs,
        "unrelated_key": "Should not be extracted"
    }
    
    # Execute extraction
    await extract_and_store_facts("test_user_123", mock_state)
    
    # Assert model was configured as expected (gemini-3-flash-preview)
    MockChatLLM.assert_called_once_with(
        model=GEMINI_MODEL, 
        temperature=0.1, 
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "duper-project-1"), 
        location="global",
        client_options={"api_endpoint": "https://aiplatform.googleapis.com"}
    )
    
    # Assert the prompt generation successfully truncated the giant strings
    call_args = mock_llm_instance.ainvoke.call_args[0][0] # messages list
    assert len(call_args) == 2
    system_prompt = call_args[0].content
    human_payload = call_args[1].content
    
    assert "Extract the holistic project outcome" in system_prompt
    assert "Should not be extracted" not in human_payload
    # Ensure massive strings were truncated (won't be full length in payload)
    assert len(human_payload) < len(giant_tf) + len(giant_logs)
    
    # Assert MemoryBank was called with the summarized LLM response
    MockMemoryBank.assert_called_once_with(user_id="test_user_123")
    mock_bank_instance.generate_memories.assert_called_once_with("User wanted a secure AWS 3-tier app. Outcome: Failed due to VPC limit.")
