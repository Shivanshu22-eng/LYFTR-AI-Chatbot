"""
Tests for upgraded LYFTR AI features:
- SQLite persistence across restart (sessions, messages, image_analyses, weather_queries, crop_recommendations)
- Multimodal image upload validation (type, size) & cache bypass
- Weather error handling (invalid location, API failure)
- Crop recommendation engine variation across soils, seasons, and weather
"""

import io
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient, ASGITransport

import app.database as db
from app.main import app
from app.crop_service import recommend_crops


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_features.db")
    monkeypatch.setattr(db, "DATABASE_PATH", test_db)
    db.init_db()
    return test_db


class TestDatabasePersistence:
    def test_persistence_across_reinit(self, isolated_db):
        sess = db.create_session("Agronomy Check")
        db.save_message(sess["id"], "user", "Hello DB")
        db.save_image_analysis("leaf.png", "image/png", "Check leaf", "Healthy green leaf", session_id=sess["id"])
        db.save_weather_query("Pune", "Pune, Maharashtra, India", 18.5, 73.8, 28.0, 60.0, 0.0, 10.0, "Clear sky", "Open-Meteo", "2026-11-26T00:00", session_id=sess["id"])
        db.save_crop_recommendation("Pune", "loamy", 6.5, "Rabi", 20.0, 40.0, "moderate", "[]", "[]", session_id=sess["id"])

        # Simulate application restart by calling init_db() again on same file
        db.init_db()

        assert db.get_session(sess["id"])["title"] == "Agronomy Check"
        assert len(db.get_messages(sess["id"])) == 1
        assert db.get_image_analyses(sess["id"])[0]["filename"] == "leaf.png"
        assert db.get_weather_queries(sess["id"])[0]["resolved_name"] == "Pune, Maharashtra, India"
        assert db.get_crop_recommendations(sess["id"])[0]["soil_type"] == "loamy"


class TestImageAnalysisEndpoint:
    @pytest.mark.asyncio
    async def test_rejects_invalid_file_type(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/analyze-image",
                files={"file": ("notes.txt", b"hello world", "text/plain")},
                data={"prompt": "Describe"},
            )
        assert resp.status_code == 400
        assert "Unsupported image format" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_rejects_oversized_file(self):
        transport = ASGITransport(app=app)
        big_bytes = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (5 * 1024 * 1024 + 10))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/analyze-image",
                files={"file": ("huge.png", big_bytes, "image/png")},
                data={"prompt": "Describe"},
            )
        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_valid_image_bypasses_cache_and_persists(self):
        fake_ai = {
            "content": "Green crop leaf with no visible blight.",
            "model": "gemini/gemini-3.5-flash-lite",
            "resolution_source": "LIVE_INFERENCE",
            "latency_ms": 420.0,
            "input_tokens": 120,
            "output_tokens": 15,
            "key_id": "key-1",
            "fallback_attempts": 0,
        }
        sess = db.create_session("Image Session")
        with patch("app.main.analyze_image_with_gemini", new=AsyncMock(return_value=fake_ai)) as mock_fn:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/analyze-image",
                    files={"file": ("crop.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
                    data={"prompt": "Check crop", "session_id": sess["id"]},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cache_bypassed"] is True
        assert body["metadata"]["resolution_source"] == "LIVE_INFERENCE"
        assert "Green crop leaf" in body["analysis"]
        mock_fn.assert_awaited_once()
        assert len(db.get_image_analyses(sess["id"])) == 1
        assert len(db.get_messages(sess["id"])) == 2


class TestWeatherEndpoint:
    @pytest.mark.asyncio
    async def test_invalid_location_returns_404(self):
        with patch("app.main.fetch_live_weather", new=AsyncMock(side_effect=ValueError("Location 'ZzzNotACity' could not be found."))):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/weather", params={"location": "ZzzNotACity"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_api_failure_returns_503(self):
        with patch("app.main.fetch_live_weather", new=AsyncMock(side_effect=RuntimeError("Weather API request failed"))):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/weather", params={"location": "London"})
        assert resp.status_code == 503


class TestCropRecommendationEngine:
    def test_recommendations_vary_by_soil_and_weather(self):
        cool_rabi = recommend_crops(
            location="Punjab",
            soil_type="loamy",
            soil_ph=6.8,
            season="Rabi",
            temperature_c=18.0,
            rainfall_mm=45.0,
            irrigation="moderate",
        )
        hot_arid = recommend_crops(
            location="Rajasthan",
            soil_type="sandy",
            soil_ph=7.5,
            season="Kharif",
            temperature_c=33.0,
            rainfall_mm=30.0,
            irrigation="rainfed",
        )
        top_cool = cool_rabi["recommendations"][0]["crop"]
        top_hot = hot_arid["recommendations"][0]["crop"]
        assert top_cool != top_hot
        assert cool_rabi["scoring_methodology"]
        assert cool_rabi["assumptions"] == []

    def test_missing_soil_info_records_assumptions(self):
        res = recommend_crops(temperature_c=24.0, rainfall_mm=60.0)
        assert any("Soil type was not specified" in a for a in res["assumptions"])
        assert any("Soil pH was not provided" in a for a in res["assumptions"])
