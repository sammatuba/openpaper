"""Version tags as the server issued them, whatever a proxy did to them on the way out."""
import re

# A compressing proxy (Caddy's `encode`, a CDN) appends the encoding to an ETag and may mark it
# weak. The client can only send back what it received, so a conditional write must compare the
# tag the server issued. Tags issued here never end in one of these suffixes.
_ENCODING_SUFFIX = re.compile(r'-(?:gzip|zstd|br|deflate)"$')


def issued_tag(value: str | None) -> str | None:
    """Return an If-Match value with a weak marker and a proxy's encoding suffix removed."""
    if value is None:
        return None
    value = value.strip()
    if value.startswith("W/"):
        value = value[2:]
    return _ENCODING_SUFFIX.sub('"', value)
