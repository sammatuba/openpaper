"""Safe URL normalization and fetching for authenticated MCP PDF imports.

This is deliberately narrower than the browser's general URL import endpoint.
Only exact publisher hosts and PDF URLs are accepted. No private network fetches.
"""
import ipaddress
import re
import socket
from urllib.parse import parse_qs, quote, urlsplit

import requests

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


def normalize_research_pdf_url(url: str) -> tuple[str, str]:
    """Return (stable source key, canonical downloadable PDF URL).

    Landing-page conversion is supported only for arXiv and OpenReview.
    Other publishers require a verified direct HTTPS PDF URL.
    """
    if not isinstance(url, str) or len(url) > 2048:
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
        return f"arxiv:{arxiv_id.lower()}", f"https://arxiv.org/pdf/{arxiv_id}.pdf"
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
    return f"pdf:{hostname}{p.path}?{p.query}", url


def _require_public_dns(host: str) -> None:
    """Reject obvious DNS exposure to internal networks before connecting."""
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Research publisher DNS resolution failed") from exc
    if not records:
        raise ValueError("Research publisher has no IP addresses")
    for record in records:
        addr = ipaddress.ip_address(record[4][0])
        if not addr.is_global:
            raise ValueError("Research publisher resolves to a non-public network")


async def fetch_research_pdf(url: str) -> bytes:
    """Fetch with no redirects; enforce a hard byte cap and real PDF validation."""
    p = urlsplit(url)
    if (p.scheme != "https" or (p.hostname or "").lower() not in _ALLOWED_PDF_HOSTS
            or p.username or p.password or p.port not in (None, 443)):
        raise ValueError("Unapproved PDF download URL")
    _require_public_dns(p.hostname)
    try:
        with requests.get(url, timeout=(8, 35), stream=True, allow_redirects=False,
                          headers={"User-Agent": _UA, "Accept": "application/pdf"}) as response:
            if 300 <= response.status_code < 400:
                raise ValueError("PDF redirect rejected; supply an approved final PDF URL")
            response.raise_for_status()
            max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
            parts = []
            size = 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("PDF exceeds configured upload-size limit")
                parts.append(chunk)
            data = b"".join(parts)
    except requests.RequestException as exc:
        raise ValueError("Research PDF download failed") from exc
    valid, reason = await validate_pdf_content(data, source="MCP research URL")
    if not valid:
        raise ValueError(f"Invalid research PDF: {reason}")
    return data
