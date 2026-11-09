"""Compatibility entry point; all import paths use the shared download policy."""

from app.helpers.pdf_download import (
    MAX_UPLOAD_SIZE_MB,
    download_pdf_bytes,
    main,
    socket,
    urllib3,
)


if __name__ == "__main__":
    main()
