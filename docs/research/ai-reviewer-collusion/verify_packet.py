#!/usr/bin/env python3
"""Verify candidate evidence provenance without network or research-model calls.

Source files are untrusted data. This checker never executes their content.
The --source-dir option requires the original downloaded HTML/PDF bytes.
"""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
EXPECTED_REFERENCES = {"R11", "R12", "R14", "R15", "R17", "S1", "T17"}
PROJECT_ID = "a5cf0e26-f8dd-424c-a452-dbcf6ebba946"
HASH = re.compile(r"[0-9a-f]{64}\Z")


class BlockTextParser(HTMLParser):
    """html-block-text-v1: collapse whitespace inside nonempty block lines."""

    blocks = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "figcaption"}

    def __init__(self) -> None:
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in self.blocks:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.skip -= 1
        if tag in self.blocks:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(
            " ".join(line.split())
            for line in "".join(self.parts).splitlines()
            if line.strip()
        )


def sha256(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def extract(path: Path, normalization: str) -> tuple[str, list[str] | None]:
    if normalization == "html-block-text-v1":
        parser = BlockTextParser()
        parser.feed(path.read_text(encoding="utf-8"))
        return parser.text(), None
    if normalization == "pypdf-plain-pages-v1":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF verification requires the server virtual environment's pypdf") from exc
        pages = [
            " ".join(page.extract_text(extraction_mode="plain").split())
            for page in PdfReader(path).pages
        ]
        return "\n".join(pages), pages
    raise ValueError("Unsupported extraction normalization")


def verify(source_dir: Path | None = None) -> dict:
    catalog = json.loads((ROOT / "sources.json").read_text())
    ledger = json.loads((ROOT / "evidence.json").read_text())
    require(catalog["schema_version"] == ledger["schema_version"] == 1, "Schema version mismatch")
    require(catalog["project_id"] == PROJECT_ID, "Unexpected project identity")
    sources = {source["reference_id"]: source for source in catalog["sources"]}
    require(len(sources) == len(catalog["sources"]), "Duplicate source reference")
    require(set(sources) == EXPECTED_REFERENCES, "Source set differs from inspected bibliography")
    entries = ledger["entries"]
    require(12 <= len(entries) <= 20, "Unexpected candidate evidence count")
    require(len({row["id"] for row in entries}) == len(entries), "Duplicate evidence ID")
    quote_counts = {ref: 0 for ref in sources}
    extracted: dict[str, tuple[str, list[str] | None]] = {}
    for ref, source in sources.items():
        for field in ("raw_sha256", "normalized_text_sha256"):
            require(bool(HASH.fullmatch(source[field])), f"{ref}: malformed {field}")
        name = source["raw_file"]
        require(name == Path(name).name and name in {ref + ".html", ref + ".pdf"}, f"{ref}: unsafe source filename")
        require(source["canonical_dossier_updated"] is False, f"{ref}: staged packet must not claim canonical promotion")
        for field in ("landing_url", "full_text_url"):
            url = urlsplit(source[field])
            require(url.scheme == "https" and bool(url.hostname) and not url.username and not url.password, f"{ref}: invalid public source URL")
        if source_dir is not None:
            path = (source_dir / name).resolve()
            require(path.is_relative_to(source_dir.resolve()), f"{ref}: source path escapes selected directory")
            raw = path.read_bytes()
            require(len(raw) == source["raw_bytes"], f"{ref}: primary input size changed")
            require(sha256(raw) == source["raw_sha256"], f"{ref}: primary input hash changed")
            text, pages = extract(path, source["normalization"])
            require(len(text) == source["normalized_text_characters"], f"{ref}: extracted length changed")
            require(sha256(text) == source["normalized_text_sha256"], f"{ref}: extracted text hash changed")
            extracted[ref] = text, pages
    for row in entries:
        ref = row["reference_id"]
        require(ref in sources, "Evidence refers to an unregistered source")
        require(row["review_status"] == "candidate", f"{row['id']}: requires explicit review before promotion")
        require(row["supports_hypothesis_empirically"] is False, f"{row['id']}: literature record is not our experimental result")
        quote = row["excerpt"]
        require(isinstance(quote, str) and bool(quote.strip()), f"{row['id']}: empty excerpt")
        require(sha256(quote) == row["excerpt_sha256"], f"{row['id']}: excerpt changed")
        quote_counts[ref] += len(quote.split())
        loc = row["source_location"]
        start, end = loc["normalized_character_start_0based"], loc["normalized_character_end_exclusive"]
        require(type(start) is int and type(end) is int and 0 <= start < end, f"{row['id']}: invalid offsets")
        require(end - start == len(quote), f"{row['id']}: offset length mismatch")
        require(end <= sources[ref]["normalized_text_characters"], f"{row['id']}: offset beyond source")
        require(type(loc["normalized_line_1based"]) is int and loc["normalized_line_1based"] >= 1, f"{row['id']}: invalid line")
        page = loc["pdf_page_1based"]
        require(page is None or (type(page) is int and page >= 1), f"{row['id']}: invalid PDF page")
        if source_dir is not None:
            text, pages = extracted[ref]
            require(text[start:end] == quote, f"{row['id']}: excerpt differs from primary text")
            require(text[:start].count("\n") + 1 == loc["normalized_line_1based"], f"{row['id']}: line location changed")
            if pages is not None:
                require(page is not None and page <= len(pages) and quote in pages[page - 1], f"{row['id']}: PDF location mismatch")
            else:
                require(page is None, f"{row['id']}: HTML must not invent a PDF page")
    require(all(0 < count <= 25 for count in quote_counts.values()), "Per-source quote budget exceeded or source unused")
    return {
        "sources": len(sources),
        "candidate_evidence_records": len(entries),
        "quoted_words_by_reference": quote_counts,
        "primary_inputs_reverified": source_dir is not None,
        "network_calls": 0,
        "canonical_records_modified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.source_dir), indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"Packet verification failed: {exc}\n")


if __name__ == "__main__":
    main()
