"""MCP transport and discovery checks with a fake verified bearer."""
import os
import unittest
from unittest.mock import patch



class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_unauthorized_and_initialization(self):
        import httpx
        from fastmcp.server.auth.auth import AccessToken
        from fastmcp.server.auth.providers.google import GoogleProvider
        from app.mcp.server import create_mcp_app
        async def verify(_self, token):
            return AccessToken(token=token, client_id="test", scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
                               claims={"email":"owner@example.test", "email_verified": True, "aud":"test-client"}) if token == "valid" else None
        with patch.object(GoogleProvider, "verify_token", verify):
            from fastapi import FastAPI
            mcp_app = create_mcp_app()
            app = FastAPI(lifespan=mcp_app.lifespan)
            app.mount("/", mcp_app)
            async with mcp_app.lifespan(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://papers.example.workers.dev") as client:
                    discovery = await client.get("/.well-known/oauth-protected-resource/api/mcp")
                    self.assertEqual(discovery.status_code, 200)
                    self.assertEqual(discovery.json()["resource"], "https://papers.example.workers.dev/api/mcp")
                    payload = {"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{"protocolVersion":"2025-03-26", "capabilities":{}, "clientInfo":{"name":"test", "version":"1"}}}
                    headers = {"accept":"application/json, text/event-stream"}
                    self.assertEqual((await client.post("/api/mcp", json=payload, headers=headers)).status_code, 401)
                    response = await client.post("/api/mcp", json=payload, headers={**headers, "authorization":"Bearer valid"})
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("protocolVersion", response.text)
