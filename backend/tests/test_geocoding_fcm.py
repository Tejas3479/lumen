import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.geo_utils import reverse_geocode
from app.services.notification import send_push_notification

@pytest.mark.asyncio
async def test_google_geocoding_success():
    with patch("app.services.geo_utils.settings") as mock_settings:
        mock_settings.google_api_key = "test-google-maps-key"
        
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "status": "OK",
            "results": [{
                "formatted_address": "Test Road, Ward 1, City",
                "address_components": [
                    {"long_name": "Test Road", "types": ["route"]},
                    {"long_name": "Ward 1", "types": ["sublocality_level_1"]},
                    {"long_name": "City", "types": ["locality"]},
                    {"long_name": "State", "types": ["administrative_area_level_1"]},
                    {"long_name": "560001", "types": ["postal_code"]},
                ]
            }]
        })
        
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            res = await reverse_geocode(12.9716, 77.5946)
            assert res is not None
            assert res["source"] == "google"
            assert res["address"] == "Test Road, Ward 1, City"
            assert res["ward"] == "Ward 1"
            assert res["city"] == "City"
            assert res["postcode"] == "560001"


@pytest.mark.asyncio
async def test_geocoding_fallback_to_nominatim():
    with patch("app.services.geo_utils.settings") as mock_settings:
        mock_settings.google_api_key = None
        mock_settings.nominatim_url = "https://nominatim.test"
        mock_settings.geocoding_user_agent = "test-agent"
        
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "address": {
                "road": "OSM Road",
                "suburb": "OSM Suburb",
                "city": "OSM City",
                "state": "OSM State",
                "postcode": "560002"
            }
        })
        
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            
            res = await reverse_geocode(12.9716, 77.5946)
            assert res is not None
            assert res["source"] == "nominatim"
            assert res["address"] == "OSM Road, OSM Suburb, OSM City"
            assert res["ward"] == "OSM Suburb"


@pytest.mark.asyncio
async def test_send_push_notification_fcm_first():
    with patch("app.services.notification.settings") as mock_settings:
        mock_settings.firebase_credentials_path = "/test/path.json"
        mock_settings.fcm_enabled = True
        
        subscription = {
            "fcm_token": "test-fcm-token"
        }
        
        with patch("app.services.notification.send_fcm_notification", new_callable=AsyncMock) as mock_fcm:
            mock_fcm.return_value = True
            
            success = await send_push_notification(subscription, "title", "body")
            assert success is True
            mock_fcm.assert_called_once_with(
                fcm_token="test-fcm-token",
                title="title",
                body="body",
                data={"url": "/", "tag": "lumen"}
            )
