import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.mjs";

const env = { UPSTREAM_ORIGIN: "https://openpaper-123.region.run.app" };
test("forwards only to configured origin, preserves credentials and streams", async () => {
  const original = globalThis.fetch;
  let seen;
  globalThis.fetch = async (request) => {
    seen = request;
    return new Response(new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode("stream")); c.close(); } }),
      { status: 200, headers: { "set-cookie": "session_token=abc; Secure; HttpOnly" } });
  };
  try {
    const request = new Request("https://papers.example.workers.dev//evil.example/path?q=1", {
      method: "POST", headers: { cookie: "session_token=abc", authorization: "Bearer token", "x-forwarded-host": "evil.example" },
      body: "body", duplex: "half" });
    const response = await worker.fetch(request, env);
    assert.equal(seen.url, "https://openpaper-123.region.run.app//evil.example/path?q=1");
    assert.equal(seen.headers.get("cookie"), "session_token=abc");
    assert.equal(seen.headers.get("authorization"), "Bearer token");
    assert.equal(seen.headers.get("x-forwarded-host"), "papers.example.workers.dev");
    assert.equal(seen.redirect, "manual");
    assert.equal(await seen.text(), "body");
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.match(response.headers.get("set-cookie"), /session_token/);
    assert.equal(await response.text(), "stream");
  } finally { globalThis.fetch = original; }
});
test("rewrites same-origin redirects, rejects invalid upstream", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(null, { status: 307,
    headers: { location: env.UPSTREAM_ORIGIN + "/api/path/?x=1" } });
  try {
    const request = new Request("https://papers.example.workers.dev/api/path");
    const response = await worker.fetch(request, env);
    assert.equal(response.headers.get("location"), "https://papers.example.workers.dev/api/path/?x=1");
    assert.equal((await worker.fetch(request, { UPSTREAM_ORIGIN: "https://evil.example" })).status, 503);
  } finally { globalThis.fetch = original; }
});
