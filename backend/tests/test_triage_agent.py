import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.triage_agent import run_triage_agent, _call_gemini_with_tools

@pytest.mark.asyncio
async def test_call_gemini_with_tools_success():
    with patch("app.services.triage_agent.settings") as mock_settings:
        mock_settings.google_api_key = "test-google-key"
        
        # Iteration 1: model returns tool call (get_department_recommendation)
        # Iteration 2: model returns final recommendation JSON
        mock_response_1 = MagicMock()
        mock_response_1.raise_for_status = MagicMock()
        mock_response_1.json = MagicMock(return_value={
            "candidates": [{
                "content": {
                    "parts": [
                        {
                            "text": "I will check the department recommendation first."
                        },
                        {
                            "functionCall": {
                                "name": "get_department_recommendation",
                                "args": {"category": "pothole", "severity": "high"}
                            }
                        }
                    ]
                }
            }]
        })
        
        mock_response_2 = MagicMock()
        mock_response_2.raise_for_status = MagicMock()
        mock_response_2.json = MagicMock(return_value={
            "candidates": [{
                "content": {
                    "parts": [
                        {
                            "text": '{"recommended_department": "BBMP Roads", "recommended_priority": 3, "recommended_action": "auto_assign", "recommendation_summary": "Auto-assigned to BBMP Roads", "confidence": 0.95}'
                        }
                    ]
                }
            }]
        })
        
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [mock_response_1, mock_response_2]
            
            text, tool_calls, steps = await _call_gemini_with_tools("system prompt", "user message")
            assert "BBMP Roads" in text
            assert len(tool_calls) == 1
            assert tool_calls[0]["tool"] == "get_department_recommendation"
            assert any(s.get("type") == "tool_call" and s.get("tool") == "get_department_recommendation" for s in steps)
            assert any(s.get("type") == "tool_result" and s.get("tool") == "get_department_recommendation" for s in steps)


@pytest.mark.asyncio
async def test_run_triage_agent():
    issue_id = uuid.uuid4()
    
    mock_db = AsyncMock()
    
    # Mock issue result
    mock_issue = MagicMock()
    mock_issue.id = issue_id
    mock_issue.title = "Broken road"
    mock_issue.description = "Giant pothole on main road"
    mock_issue.ai_category = "pothole"
    mock_issue.severity = "high"
    mock_issue.ai_severity = "high"
    mock_issue.is_emergency = False
    mock_issue.latitude = 12.9716
    mock_issue.longitude = 77.5946
    mock_issue.address = "Test Street"
    mock_issue.ward = "Koramangala"
    mock_issue.verification_count = 0
    mock_issue.ai_confidence = 0.9
    
    mock_res_1 = MagicMock()
    mock_res_1.scalar_one_or_none.return_value = mock_issue
    
    mock_res_2 = MagicMock()
    mock_res_2.all.return_value = [("Nearby pothole", "reported", "pothole")]
    
    mock_res_3 = MagicMock()
    mock_res_3.scalar_one.return_value = 5
    
    mock_db.execute.side_effect = [mock_res_1, mock_res_2, mock_res_3]
    
    with patch("app.services.triage_agent._call_gemini_with_tools", new_callable=AsyncMock) as mock_agent_call:
        mock_agent_call.return_value = (
            '{"recommended_department": "BBMP Roads", "recommended_priority": 3, "recommended_action": "auto_assign", "recommendation_summary": "Auto-assigned to BBMP Roads", "confidence": 0.95}',
            [{"tool": "get_department_recommendation"}],
            []
        )
        
        result = await run_triage_agent(issue_id, mock_db)
        assert result["recommended_department"] == "BBMP Roads"
        assert result["recommended_priority"] == 3
        assert result["recommended_action"] == "auto_assign"
        assert result["confidence"] == 0.95
        
        # Verify db.add was called
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
