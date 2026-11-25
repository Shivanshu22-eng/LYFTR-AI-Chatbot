"""
Tests for new LYFTR AI features:
- Authentication (register, login, JWT, role-based access)
- Image generation (endpoint, content policy, daily limits)
- Admin management (user permissions, settings, audit logs)
- Security (unauthorized access, role escalation prevention)
"""

import json
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

import app.database as db
from app.main import app
from app.auth_service import hash_password, verify_password, create_access_token, decode_access_token
from app.image_service import _check_content_policy, _build_prompt, STYLE_PROMPTS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own fresh SQLite database."""
    test_db = str(tmp_path / "test_new_features.db")
    monkeypatch.setattr(db, "DATABASE_PATH", test_db)
    db.init_db()
    return test_db


@pytest.fixture
def admin_user(isolated_db):
    """Create an admin user and return (user, token)."""
    pw_hash = hash_password("adminpass123")
    user = db.create_user("admin@test.com", pw_hash, role="admin")
    token = create_access_token({"sub": user["id"], "email": user["email"], "role": "admin"})
    return user, token


@pytest.fixture
def regular_user(isolated_db):
    """Create a regular user and return (user, token)."""
    pw_hash = hash_password("userpass123")
    user = db.create_user("user@test.com", pw_hash, role="user")
    token = create_access_token({"sub": user["id"], "email": user["email"], "role": "user"})
    return user, token


@pytest.fixture
def creator_user(isolated_db):
    """Create an authorized_creator user."""
    pw_hash = hash_password("creatorpass123")
    user = db.create_user("creator@test.com", pw_hash, role="authorized_creator")
    db.update_user_permissions(user["id"], allowed_categories=["safe", "adult"])
    token = create_access_token({"sub": user["id"], "email": user["email"], "role": "authorized_creator"})
    return user, token


# ---------------------------------------------------------------------------
# Auth service unit tests
# ---------------------------------------------------------------------------

class TestAuthService:
    def test_hash_and_verify_password(self):
        hashed = hash_password("MySecurePass123!")
        assert verify_password("MySecurePass123!", hashed)
        assert not verify_password("WrongPassword", hashed)
        assert not verify_password("", hashed)

    def test_create_and_decode_token(self):
        token = create_access_token({"sub": "user-123", "role": "user"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["role"] == "user"
        assert "exp" in payload

    def test_tampered_token_rejected(self):
        token = create_access_token({"sub": "user-123"})
        parts = token.split(".")
        # Tamper with the payload
        tampered = f"{parts[0]}.INVALIDPAYLOAD.{parts[2]}"
        assert decode_access_token(tampered) is None

    def test_invalid_token_rejected(self):
        assert decode_access_token("not.a.token") is None
        assert decode_access_token("") is None
        assert decode_access_token("only.two") is None


# ---------------------------------------------------------------------------
# Auth endpoint tests
# ---------------------------------------------------------------------------

class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_register_success(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/auth/register", json={
                "email": "newuser@test.com",
                "password": "securepass123"
            })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["email"] == "newuser@test.com"
        assert data["role"] == "user"  # Always starts as user

    @pytest.mark.asyncio
    async def test_register_duplicate_email_rejected(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/auth/register", json={
                "email": "dup@test.com", "password": "pass12345"
            })
            resp = await client.post("/auth/register", json={
                "email": "dup@test.com", "password": "different123"
            })
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_cannot_self_assign_admin_role(self):
        """Registration always creates a 'user' role regardless of any payload manipulation."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/auth/register", json={
                "email": "hacker@test.com", "password": "hackpass123"
            })
        assert resp.status_code == 201
        assert resp.json()["role"] == "user"

    @pytest.mark.asyncio
    async def test_login_success(self, regular_user):
        _, _ = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/auth/login", json={
                "email": "user@test.com", "password": "userpass123"
            })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    @pytest.mark.asyncio
    async def test_login_wrong_password_rejected(self, regular_user):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/auth/login", json={
                "email": "user@test.com", "password": "wrongpassword"
            })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_returns_user_profile(self, regular_user):
        user, token = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "user@test.com"
        assert data["role"] == "user"

    @pytest.mark.asyncio
    async def test_suspended_user_cannot_login(self, regular_user):
        user, _ = regular_user
        db.update_user_permissions(user["id"], is_active=False)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/auth/login", json={
                "email": "user@test.com", "password": "userpass123"
            })
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Image service unit tests
# ---------------------------------------------------------------------------

class TestImageService:
    def test_content_policy_blocks_explicit_for_regular_user(self):
        error = _check_content_policy("nude woman portrait", "user", ["safe"])
        assert error is not None
        assert "Authorized Creator" in error

    def test_content_policy_allows_safe_content(self):
        error = _check_content_policy("beautiful mountain landscape", "user", ["safe"])
        assert error is None

    def test_content_policy_blocks_csam_for_everyone(self):
        error = _check_content_policy("child abuse image", "admin", ["safe", "adult"])
        assert error is not None

    def test_content_policy_allows_adult_for_authorized_creator(self):
        # 'nude' is blocked for regular users but allowed for authorized_creator with adult category
        error = _check_content_policy("artistic nude portrait", "authorized_creator", ["safe", "adult"])
        assert error is None

    def test_style_prompt_modifier_applied(self):
        prompt = _build_prompt("a cat", "cinematic")
        assert "cinematic" in prompt.lower()
        assert "a cat" in prompt.lower()

    def test_unknown_style_falls_back_gracefully(self):
        prompt = _build_prompt("a dog", "unknown_style_xyz")
        assert "a dog" in prompt


# ---------------------------------------------------------------------------
# Image generation endpoint tests
# ---------------------------------------------------------------------------

class TestImageGenerationEndpoints:
    @pytest.mark.asyncio
    async def test_generate_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/images/generate", json={
                "prompt": "A beautiful sunset", "style": "photorealistic"
            })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_blocked_when_global_disabled(self, regular_user):
        _, token = regular_user
        db.set_setting("image_generation_enabled", "false")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/images/generate",
                json={"prompt": "A sunset", "style": "photorealistic"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
        assert "disabled" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_generate_blocked_explicit_content_regular_user(self, regular_user):
        _, token = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/images/generate",
                json={"prompt": "naked person photo", "style": "photorealistic"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403
        assert "Authorized Creator" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_generate_success_mocked(self, regular_user):
        _, token = regular_user
        mock_result = {
            "prompt": "A mountain",
            "style": "photorealistic",
            "aspect_ratio": "1:1",
            "images": [{"image_url": "https://image.pollinations.ai/prompt/test", "variation_index": 1,
                         "provider": "pollinations.ai", "model": "flux", "latency_ms": 500}],
            "errors": [], "total_requested": 1, "total_generated": 1,
        }
        with patch("app.main.generate_images", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_result
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/images/generate",
                    json={"prompt": "A mountain", "style": "photorealistic"},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["images"]) == 1
        assert "id" in data

    @pytest.mark.asyncio
    async def test_daily_limit_enforced(self, regular_user):
        user, token = regular_user
        # Set limit to 0
        db.update_user_permissions(user["id"], daily_gen_limit=0)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/images/generate",
                json={"prompt": "Test", "style": "photorealistic"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_history_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/images/history")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_history_returns_user_records(self, regular_user):
        user, token = regular_user
        # Insert a record directly
        db.save_image_generation(
            user_id=user["id"], prompt="sunset", style="photorealistic",
            aspect_ratio="1:1", num_images=1, images_json="[]",
            provider="pollinations.ai", model="flux",
            latency_ms=500, status="success",
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/images/history",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["prompt"] == "sunset"

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_users_image(self, regular_user, admin_user):
        """A regular user cannot access another user's image generation record."""
        admin, admin_token = admin_user
        user, user_token = regular_user
        # Admin creates an image record
        record = db.save_image_generation(
            user_id=admin["id"], prompt="admin image", style="photorealistic",
            aspect_ratio="1:1", num_images=1, images_json="[]",
            provider="pollinations.ai", model="flux",
            latency_ms=100, status="success",
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/images/{record['id']}",
                                    headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin endpoint tests
# ---------------------------------------------------------------------------

class TestAdminEndpoints:
    @pytest.mark.asyncio
    async def test_admin_list_users_requires_admin(self, regular_user):
        _, token = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/users",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_list_users(self, admin_user, regular_user):
        _, admin_token = admin_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/users",
                                    headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        users = resp.json()
        emails = [u["email"] for u in users]
        assert "user@test.com" in emails

    @pytest.mark.asyncio
    async def test_admin_update_user_role(self, admin_user, regular_user):
        _, admin_token = admin_user
        user, _ = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch(
                f"/admin/users/{user['id']}/permissions",
                json={"role": "authorized_creator", "daily_gen_limit": 50},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["role"] == "authorized_creator"
        assert updated["daily_gen_limit"] == 50

    @pytest.mark.asyncio
    async def test_admin_suspend_user(self, admin_user, regular_user):
        _, admin_token = admin_user
        user, _ = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch(
                f"/admin/users/{user['id']}/permissions",
                json={"is_active": False},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["is_active"] == False

    @pytest.mark.asyncio
    async def test_admin_cannot_demote_self(self, admin_user):
        admin, admin_token = admin_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch(
                f"/admin/users/{admin['id']}/permissions",
                json={"role": "user"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_update_image_settings(self, admin_user):
        _, admin_token = admin_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch(
                "/admin/settings/image-generation",
                json={"image_generation_enabled": False, "image_generation_default_daily_limit": 5},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        settings = resp.json()
        assert settings.get("image_generation_enabled") == "false"
        assert settings.get("image_generation_default_daily_limit") == "5"

    @pytest.mark.asyncio
    async def test_audit_log_created_on_permission_change(self, admin_user, regular_user):
        _, admin_token = admin_user
        user, _ = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.patch(
                f"/admin/users/{user['id']}/permissions",
                json={"role": "authorized_creator"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            resp = await client.get("/admin/audit-logs",
                                    headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        logs = resp.json()
        assert len(logs) >= 1
        assert logs[0]["action"] == "update_user_permissions"

    @pytest.mark.asyncio
    async def test_regular_user_cannot_access_admin_audit_logs(self, regular_user):
        _, token = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/audit-logs",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_revoked_user_cannot_generate_images(self, admin_user, regular_user):
        """After admin suspends a user, their token should be rejected for image gen."""
        _, admin_token = admin_user
        user, user_token = regular_user
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Admin suspends the user
            await client.patch(
                f"/admin/users/{user['id']}/permissions",
                json={"is_active": False},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            # Suspended user tries to generate
            resp = await client.post(
                "/images/generate",
                json={"prompt": "A sunset", "style": "photorealistic"},
                headers={"Authorization": f"Bearer {user_token}"},
            )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_unauthenticated_admin_endpoint_rejected(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/admin/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Database tests
# ---------------------------------------------------------------------------

class TestDatabaseNew:
    def test_create_and_get_user(self):
        pw_hash = hash_password("testpass")
        user = db.create_user("test@example.com", pw_hash, role="user")
        fetched = db.get_user_by_email("test@example.com")
        assert fetched is not None
        assert fetched["email"] == "test@example.com"
        assert fetched["role"] == "user"

    def test_update_user_permissions(self):
        pw_hash = hash_password("testpass")
        user = db.create_user("perm@test.com", pw_hash)
        db.update_user_permissions(
            user["id"], role="authorized_creator", daily_gen_limit=25,
            allowed_categories=["safe", "adult"]
        )
        updated = db.get_user_by_id(user["id"])
        assert updated["role"] == "authorized_creator"
        assert updated["daily_gen_limit"] == 25

    def test_save_and_get_image_generation(self):
        pw_hash = hash_password("testpass")
        user = db.create_user("imgtest@test.com", pw_hash)
        record = db.save_image_generation(
            user_id=user["id"], prompt="test prompt", style="cinematic",
            aspect_ratio="16:9", num_images=2, images_json='[]',
            provider="pollinations.ai", model="flux",
            latency_ms=1200.0, status="success",
        )
        assert record["id"] is not None
        recs = db.get_user_image_generations(user["id"])
        assert len(recs) == 1
        assert recs[0]["prompt"] == "test prompt"

    def test_settings_crud(self):
        db.set_setting("test_key", "test_value")
        assert db.get_setting("test_key") == "test_value"
        db.set_setting("test_key", "updated_value")
        assert db.get_setting("test_key") == "updated_value"

    def test_audit_log_persisted(self):
        pw_hash = hash_password("adminpass")
        admin = db.create_user("log_admin@test.com", pw_hash, role="admin")
        db.save_audit_log(admin["id"], "test_action", details="test details")
        logs = db.get_audit_logs()
        assert len(logs) >= 1
        assert logs[0]["action"] == "test_action"

    def test_count_user_generations_today(self):
        pw_hash = hash_password("testpass")
        user = db.create_user("count@test.com", pw_hash)
        assert db.count_user_generations_today(user["id"]) == 0
        db.save_image_generation(
            user_id=user["id"], prompt="test", style="photorealistic",
            aspect_ratio="1:1", num_images=1, images_json="[]",
            provider="pollinations.ai", model="flux",
            latency_ms=100, status="success",
        )
        assert db.count_user_generations_today(user["id"]) == 1
        # Failed generations don't count toward limit
        db.save_image_generation(
            user_id=user["id"], prompt="test", style="photorealistic",
            aspect_ratio="1:1", num_images=1, images_json="[]",
            provider="pollinations.ai", model="flux",
            latency_ms=None, status="failed",
        )
        assert db.count_user_generations_today(user["id"]) == 1
