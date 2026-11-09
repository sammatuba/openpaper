"""Bounded public HTTPS downloads shared by browser and MCP paper imports.

The network operation runs in a child process so its hard deadline also covers
DNS, TLS and a peer that keeps a read alive indefinitely. URLs travel on stdin
and failures expose no signed URL or underlying network diagnostics.
"""

import ipaddress
import socket
import subprocess
import sys
import time
from urllib.parse import urljoin, urlsplit

import certifi
import urllib3

MAX_UPLOAD_SIZE_MB = 30
MAX_URL_BYTES = 16000
DOWNLOAD_TIMEOUT = 60
DOWNLOAD_ERROR = "PDF download failed; use a direct public HTTPS PDF or reattach the file"


def download_pdf(url: str, *, timeout: float = DOWNLOAD_TIMEOUT) -> bytes:
    """Download within a hard deadline, killing and reaping a stalled worker."""
    if not isinstance(url, str) or not url or len(url.encode()) > MAX_URL_BYTES:
        raise ValueError("PDF URL exceeds length limit or is empty")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.helpers.pdf_download"],
            input=url.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("PDF download exceeded its deadline") from None
    except OSError:
        raise ValueError(DOWNLOAD_ERROR) from None
    if result.returncode or not result.stdout.startswith(b"1"):
        raise ValueError(DOWNLOAD_ERROR)
    data = result.stdout[1:]
    if len(data) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValueError("PDF exceeds the upload limit")
    return data


def download_pdf_bytes(url: str) -> bytes:
    """Worker: pin public addresses through TLS and revalidate every redirect."""
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT
    for _ in range(6):
        if (not isinstance(url, str) or not url or len(url.encode()) > MAX_URL_BYTES
                or any(ord(c) < 33 or ord(c) == 127 for c in url)
                or time.monotonic() > deadline):
            raise ValueError("PDF download exceeded its URL/time limit")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            raise ValueError("A public HTTPS PDF URL on port 443 is required")
        try:
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
            ips = {address[4][0] for address in addresses}
            if not ips or any(
                not (ip := ipaddress.ip_address(address)).is_global
                or ip.is_multicast or ip.is_reserved
                for address in ips
            ):
                raise ValueError("PDF URL must resolve only to public addresses")
        except socket.gaierror:
            raise ValueError("PDF host could not be resolved") from None
        pool = urllib3.HTTPSConnectionPool(
            sorted(ips)[0], port=443, server_hostname=parsed.hostname,
            assert_hostname=parsed.hostname, cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(), timeout=urllib3.Timeout(connect=5, read=10),
            retries=False,
        )
        response = None
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            response = pool.request(
                "GET", path,
                headers={"Host": parsed.hostname, "User-Agent": "OpenPaper-PDF-import/1.0",
                         "Accept": "application/pdf"},
                redirect=False, preload_content=False,
            )
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("PDF redirect has no destination")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError("PDF server did not return a downloadable PDF")
            cap = MAX_UPLOAD_SIZE_MB * 1024 * 1024
            if int(response.headers.get("Content-Length", "0")) > cap:
                raise ValueError("PDF exceeds the 30MB upload limit")
            chunks, size = [], 0
            for chunk in response.stream(65536, decode_content=True):
                size += len(chunk)
                if size > cap or time.monotonic() > deadline:
                    raise ValueError("PDF exceeds the download size/time limit")
                chunks.append(chunk)
            return b"".join(chunks)
        except (urllib3.exceptions.HTTPError, OSError):
            raise ValueError(DOWNLOAD_ERROR) from None
        finally:
            if response is not None:
                response.close()
            pool.close()
    raise ValueError("Too many PDF redirects")


def main() -> None:
    """Small binary worker protocol: success marker plus bytes, or generic error."""
    try:
        url = sys.stdin.buffer.read(MAX_URL_BYTES + 1).decode()
        data = download_pdf_bytes(url)
        sys.stdout.buffer.write(b"1" + data)
    except Exception:
        sys.stdout.buffer.write(b"0" + DOWNLOAD_ERROR.encode())


if __name__ == "__main__":
    main()
