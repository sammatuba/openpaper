// Fixed origin: never accept an upstream from the request. Bodies are passed as streams.
export default {
  async fetch(request, env) {
    let upstream;
    try {
      upstream = new URL(env.UPSTREAM_ORIGIN);
      if (upstream.protocol !== "https:" || !upstream.hostname.endsWith(".run.app") ||
          upstream.username || upstream.password || upstream.port || upstream.pathname !== "/" ||
          upstream.search || upstream.hash) throw new Error("Invalid upstream");
    } catch {
      return new Response("Proxy upstream is not configured", { status: 503 });
    }
    const incoming = new URL(request.url);
    const target = new URL(upstream);
    target.pathname = incoming.pathname;
    target.search = incoming.search;
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.delete("forwarded");
    headers.delete("x-forwarded-host");
    headers.delete("x-forwarded-proto");
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", "https");
    headers.set("cache-control", "no-store");
    // Manual redirects prevent forwarding credentials to another host.
    const response = await fetch(new Request(target, { method: request.method, headers,
      body: request.body, duplex: "half", cache: "no-store", redirect: "manual" }));
    const outputHeaders = new Headers(response.headers);
    outputHeaders.set("cache-control", "no-store");
    outputHeaders.set("cdn-cache-control", "no-store");
    outputHeaders.set("cloudflare-cdn-cache-control", "no-store");
    const location = outputHeaders.get("location");
    if (location) {
      try {
        const redirect = new URL(location, upstream);
        if (redirect.origin === upstream.origin && location.startsWith(upstream.origin)) {
          outputHeaders.set("location", incoming.origin + redirect.pathname + redirect.search + redirect.hash);
        }
      } catch { /* Leave malformed or external redirects untouched. */ }
    }
    return new Response(response.body, { status: response.status, statusText: response.statusText,
      headers: outputHeaders });
  },
};
