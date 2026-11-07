"""Safe URL normalization and fetching for authenticated MCP PDF imports.

This is deliberately narrower than the browser's general URL import endpoint.
Only exact publisher hosts and PDF URLs are accepted. No private network fetches.
"""
import asyncio
import ipaddress
import re
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, quote, urlsplit

import certifi
import urllib3

from app.helpers.parser import MAX_UPLOAD_SIZE_MB, validate_pdf_content

_ALLOWED_PDF_HOSTS = frozenset({
    "arxiv.org", "export.arxiv.org", "openreview.net", "aclanthology.org",
    "proceedings.mlr.press", "proceedings.neurips.cc", "papers.nips.cc",
    "ojs.aaai.org", "www.nature.com", "dl.acm.org", "www.sciencedirect.com",
    "www.jmlr.org", "proceedings.iclr.cc",
})
_ARXIV = re.compile(r"^(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?|[a-z-]+(?:\.[A-Z]{2})?/[0-9]{7})(?:\.pdf)?$", re.I)
_OPENREVIEW_ID = re.compile(r"^[A-Za-z0-9_-]{4,128}$")
_UA = "OpenPaper-MCP/1.0 (research PDF import)"
DOWNLOAD_TIMEOUT = 60


def normalize_research_pdf_url(url: str) -> tuple[str, str]:
    """Return (stable source key, canonical downloadable PDF URL).

    Landing-page conversion is supported only for arXiv and OpenReview.
    Other publishers require a verified direct HTTPS PDF URL.
    """
    if (not isinstance(url, str) or not url or len(url) > 2048
            or any(ord(c) < 33 or ord(c) == 127 for c in url)):
        raise ValueError("Invalid source URL")
    p = urlsplit(url)
    try:
        port = p.port
    except ValueError as exc:
        raise ValueError("Invalid port") from exc
    hostname = (p.hostname or "").lower()
    if (p.scheme != "https" or hostname not in _ALLOWED_PDF_HOSTS
            or port not in (None, 443) or p.username or p.password):
        raise ValueError("Source must be HTTPS on an approved research publisher host")
    if p.fragment:
        raise ValueError("URL fragments are not supported")
    path = p.path.lstrip("/")
    if hostname in {"arxiv.org", "export.arxiv.org"}:
        match = _ARXIV.fullmatch(path)
        if match is None or p.query:
            raise ValueError("Expected an arXiv abstract or PDF URL")
        arxiv_id = match.group(1)
        return f"arxiv:{arxiv_id.lower()}", f"https://arxiv.org/pdf/{arxiv_id}"
    if hostname == "openreview.net":
        q = parse_qs(p.query, keep_blank_values=True)
        if path not in {"forum", "pdf"} or set(q) != {"id"} or len(q["id"]) != 1:
            raise ValueError("Expected an OpenReview forum or PDF link with one id")
        paper_id = q["id"][0]
        if not _OPENREVIEW_ID.fullmatch(paper_id):
            raise ValueError("Invalid OpenReview paper ID")
        return f"openreview:{paper_id}", f"https://openreview.net/pdf?id={quote(paper_id)}"
    if not p.path.lower().endswith(".pdf"):
        raise ValueError("Publisher landing page is not a PDF; provide a direct PDF URL")
    source_key = f"pdf:{hostname}{p.path}?{p.query}"
    if len(source_key) > 600:
        raise ValueError("PDF source URL is too long for the import ledger")
    return source_key, url


def _require_public_dns(host: str) -> str:
    """Return a vetted address to pin through the actual TLS connection."""
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Research publisher DNS resolution failed") from exc
    if not records:
        raise ValueError("Research publisher has no IP addresses")
    for record in records:
        addr = ipaddress.ip_address(record[4][0])
        if not addr.is_global or addr.is_multicast or addr.is_reserved:
            raise ValueError("Research publisher resolves to a non-public network")
    return records[0][4][0]


def _download_research_pdf(url: str) -> bytes:
    """Run all blocking network I/O outside the ASGI event loop."""
    p = urlsplit(url)
    if (p.scheme != "https" or (p.hostname or "").lower() not in _ALLOWED_PDF_HOSTS
            or p.username or p.password or p.port not in (None, 443)):
        raise ValueError("Unapproved PDF download URL")
    address = _require_public_dns(p.hostname)
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    pool = urllib3.HTTPSConnectionPool(
        address, port=443, server_hostname=p.hostname, assert_hostname=p.hostname,
        cert_reqs="CERT_REQUIRED", ca_certs=certifi.where(),
        timeout=urllib3.Timeout(connect=8, read=10), retries=False,
    )
    response = None
    try:
        path = p.path + ("?" + p.query if p.query else "")
        response = pool.request("GET", path, redirect=False, preload_content=False,
                                headers={"Host": p.hostname, "User-Agent": _UA, "Accept": "application/pdf"})
        if 300 <= response.status < 400:
            raise ValueError("PDF redirect rejected; supply an approved final PDF URL")
        if response.status != 200:
            raise ValueError("Research PDF download failed")
        max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if int(response.headers.get("Content-Length", "0")) > max_bytes:
            raise ValueError("PDF exceeds configured upload-size limit")
        parts, size = [], 0
        for chunk in response.stream(65536, decode_content=True):
            size += len(chunk)
            if size > max_bytes or time.monotonic() > deadline:
                raise ValueError("PDF exceeds download size/time limit")
            parts.append(chunk)
        return b"".join(parts)
    except (urllib3.exceptions.HTTPError, OSError):
        raise ValueError("Research PDF download failed") from None
    finally:
        if response is not None:
            response.close()
        pool.close()


def _fetch_validated_pdf(url: str, *, timeout: float = DOWNLOAD_TIMEOUT) -> bytes:
    # A killable child bounds DNS, slow streams and PDF parsing as well as I/O.
    try:
        result = subprocess.run([sys.executable, "-m", "app.mcp.research_url"],
                                input=url.encode(), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError("Research PDF download/validation exceeded its deadline") from None
    if result.returncode or not result.stdout.startswith(b"1"):
        raise ValueError("Research PDF download/validation failed; check the direct PDF URL")
    data = result.stdout[1:]
    if len(data) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValueError("PDF exceeds configured upload-size limit")
    return data


async def fetch_research_pdf(url: str) -> bytes:
    """Fetch without redirects, then validate the complete bounded PDF."""
    return await asyncio.to_thread(_fetch_validated_pdf, url)


if __name__ == "__main__":
    try:
        source = sys.stdin.buffer.read(2049).decode()
        _, canonical = normalize_research_pdf_url(source)
        data = _download_research_pdf(canonical)
        valid, _ = asyncio.run(validate_pdf_content(data, source="MCP research URL"))
        if not valid:
            raise ValueError("Invalid PDF")
        sys.stdout.buffer.write(b"1" + data)
    except Exception:
        sys.stdout.buffer.write(b"0")
