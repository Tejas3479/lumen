import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.ai_categorizer import _call_gemini_vision, _run_categorization
from app.services.duplicate_detector import _get_gemini_embeddings, _compute_similarity

@pytest.mark.asyncio
async def test_call_gemini_vision_with_keys():
    # Test when google_api_key is set
    with patch("app.services.ai_categorizer.settings") as mock_settings:
        mock_settings.google_api_key = "test-google-key"
        mock_settings.gemini_api_key = "test-gemini-key"
        mock_settings.ai_timeout_seconds = 30

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"category": "pothole", "severity": "high", "confidence": 0.9}'
                    }]
                }
            }]
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            res = await _call_gemini_vision("test pothole", None)
            assert res is not None
            assert res["category"] == "pothole"
            
            # Verify URL used google_api_key and gemini-3.5-flash
            called_url = mock_post.call_args[0][0]
            assert "gemini-3.5-flash" in called_url
            assert "key=test-google-key" in called_url

        # Test when only legacy gemini_api_key is set
        mock_settings.google_api_key = None
        mock_settings.gemini_api_key = "test-legacy-key"
        
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            res = await _call_gemini_vision("test pothole", None)
            assert res is not None
            assert res["category"] == "pothole"
            
            # Verify URL used legacy gemini_api_key
            called_url = mock_post.call_args[0][0]
            assert "key=test-legacy-key" in called_url

        # Test when no keys are set
        mock_settings.google_api_key = None
        mock_settings.gemini_api_key = None
        res = await _call_gemini_vision("test pothole", None)
        assert res is None


@pytest.mark.asyncio
async def test_get_gemini_embeddings():
    with patch("app.services.duplicate_detector.settings") as mock_settings:
        mock_settings.google_api_key = "test-google-key"
        mock_settings.gemini_api_key = "test-gemini-key"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "embeddings": [
                {"values": [0.1, 0.2, 0.3]},
                {"values": [0.4, 0.5, 0.6]}
            ]
        })

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            
            embs = await _get_gemini_embeddings(["text1", "text2"])
            assert embs == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
            
            called_url = mock_post.call_args[0][0]
            assert "text-embedding-004:batchEmbedContents" in called_url
            assert "key=test-google-key" in called_url


@pytest.mark.asyncio
async def test_run_categorization_call_order():
    # Mock calls
    with patch("app.services.ai_categorizer._call_gemini_vision", new_callable=AsyncMock) as mock_gemini, \
         patch("app.services.ai_categorizer._call_openai_vision", new_callable=AsyncMock) as mock_openai, \
         patch("app.services.ai_categorizer.get_celery_session") as mock_session_ctx, \
         patch("redis.from_url") as mock_redis_from_url:
         
        # Mock database session
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session
        
        mock_issue_result = MagicMock()
        mock_issue = MagicMock()
        mock_issue_result.scalar_one_or_none.return_value = mock_issue
        mock_session.execute.return_value = mock_issue_result

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis_from_url.return_value = mock_redis
        
        # Scenario 1: Gemini succeeds
        mock_gemini.return_value = {
            "category": "pothole", "severity": "high", "confidence": 0.9,
            "explanation": "test", "summary": "test", "is_emergency": False, "reasoning": "test"
        }
        mock_openai.return_value = None
        
        res = await _run_categorization("00000000-0000-0000-0000-000000000000", None, "test pothole")
        assert res["category"] == "pothole"
        mock_gemini.assert_called_once()
        mock_openai.assert_not_called()
        
        # Reset mocks
        mock_gemini.reset_mock()
        mock_openai.reset_mock()
        
        # Scenario 2: Gemini fails, OpenAI fallback succeeds
        mock_gemini.return_value = None
        mock_openai.return_value = {
            "category": "streetlight", "severity": "low", "confidence": 0.8,
            "explanation": "test", "summary": "test", "is_emergency": False, "reasoning": "test"
        }
        
        res = await _run_categorization("00000000-0000-0000-0000-000000000000", None, "test streetlight")
        assert res["category"] == "streetlight"
        mock_gemini.assert_called_once()
        mock_openai.assert_called_once()
