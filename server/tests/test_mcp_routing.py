"""Exercise redirects and multipart bodies with the MCP root integration."""

import unittest

import httpx
from fastapi import FastAPI, File, UploadFile
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.applications import Starlette

from app.mcp.routing import MCPRouteMount


class MCPRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_redirects_preserve_body_and_project_with_mcp_enabled(self):
        app = FastAPI()

        @app.post("/api/paper/upload/")
        async def upload(file: UploadFile = File(...), project_id: str | None = None):
            return {"file": (await file.read()).decode(), "project_id": project_id}

        @app.post("/api/paper/upload/from-url/")
        async def from_url(body: dict):
            return body

        class AuthBoundary(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                response.headers["x-mcp-middleware"] = "retained"
                return response

        async def mcp_endpoint(request):
            return PlainTextResponse("MCP", status_code=401)

        mcp = Starlette(routes=[
            Route("/api/mcp", mcp_endpoint, methods=["POST"]),
            Route("/.well-known/oauth-protected-resource/api/mcp", mcp_endpoint),
            Route("/authorize", mcp_endpoint),
        ], middleware=[Middleware(AuthBoundary)])
        app.router.routes.append(MCPRouteMount("/", app=mcp))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://papers.test") as client:
            for path in ["/api/paper/upload", "/api/paper/upload/"]:
                response = await client.post(path + "?project_id=project", files={"file": ("paper.pdf", b"%PDF-fixture")}, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"file": "%PDF-fixture", "project_id": "project"})
                self.assertNotIn("x-mcp-middleware", response.headers)
                if not path.endswith("/"):
                    self.assertEqual(response.history[0].status_code, 307)
            response = await client.post("/api/paper/upload/from-url", json={"url": "https://example.test/paper.pdf"}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["url"], "https://example.test/paper.pdf")
            for path in ["/api/mcp", "/.well-known/oauth-protected-resource/api/mcp", "/authorize"]:
                response = await client.request("POST" if path == "/api/mcp" else "GET", path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["x-mcp-middleware"], "retained")
            self.assertEqual((await client.get("/api/mcp")).status_code, 405)
            self.assertEqual((await client.get("/missing")).status_code, 404)
