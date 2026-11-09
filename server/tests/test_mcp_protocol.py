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
        from app.mcp.routing import MCPRouteMount
        async def verify(_self, token):
            return AccessToken(token=token, client_id="test", scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
                               claims={"email":"owner@example.test", "email_verified": True, "aud":"test-client"}) if token == "valid" else None
        with patch.object(GoogleProvider, "verify_token", verify):
            from fastapi import FastAPI
            mcp_app = create_mcp_app()
            app = FastAPI(lifespan=mcp_app.lifespan)
            app.router.routes.append(MCPRouteMount("/", app=mcp_app))
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

                    listing=await client.post("/api/mcp",headers={**headers,"authorization":"Bearer valid"},json={"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
                    import json
                    result=listing.json() if listing.headers.get("content-type","").startswith("application/json") else json.loads(next(line[6:] for line in listing.text.splitlines() if line.startswith("data: ")))
                    tools={t['name']:t for t in result['result']['tools']}
                    self.assertEqual(len(tools),15)
                    tool=tools['upload_paper_file']
                    self.assertEqual(tool['_meta']['openai/fileParams'],['file'])
                    schema=tool['inputSchema'];file=schema['properties']['file']
                    if '$ref' in file: file=schema['$defs'][file['$ref'].split('/')[-1]]
                    self.assertEqual(set(file['properties']),{'download_url','file_id','mime_type','file_name'})
                    self.assertEqual(set(file['required']),{'download_url','file_id'})
                    self.assertFalse(tool['annotations']['readOnlyHint'])
                    self.assertTrue(tools['get_paper_upload_status']['annotations']['readOnlyHint'])
