#!/usr/bin/env python3
"""Local curated corpus inventory and conservative, resumable API import."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT.parent / "ai-safety"
MANIFEST = ROOT / "docs/work/corpus-manifest.json"
PDFS = ["2306.12001v6.pdf", "projects/2026-10-apart-collusion-sprint/report/REPORT.pdf"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identities(text):
    """Only explicit identifiers; never infer equivalence from titles."""
    result = set()
    for url in re.findall(r"https?://[^\s\"\x27<>\]}]+", text, re.I):
        url = url.rstrip(".,;")
        p = parse.urlsplit(url)
        host = (p.hostname or "").lower()
        path = p.path.rstrip("/")
        if host in ("doi.org", "dx.doi.org"):
            result.add("doi:" + parse.unquote(path.lstrip("/")).lower())
        elif host in ("arxiv.org", "www.arxiv.org", "export.arxiv.org"):
            m = re.match(r"/(?:abs|pdf|html)/(.+?)(?:\.pdf)?$", path, re.I)
            if m:
                result.add("arxiv:" + re.sub(r"v\d+$", "", m.group(1), flags=re.I).lower())
        else:
            result.add("url:" + parse.urlunsplit((p.scheme.lower(), host, path, p.query, "")))
    for doi in re.findall(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I):
        result.add("doi:" + doi.rstrip(".,;)\"").lower())
    return sorted(result)


def frontmatter(text):
    fm = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""
    # Only the flat scalar fields and explicit primary URL fields identify a work.
    # This deliberately avoids treating code and extraction references as aliases.
    fields = {}
    section = None
    for line in fm.splitlines():
        m = re.match(r"^(\s*)([a-z_]+):\s*(.*?)\s*$", line)
        if not m:
            continue
        indent, name, value = m.groups()
        if not indent:
            section = name if not value else None
            if name in ("id", "title", "status", "read_status", "updated", "doi", "arxiv", "version"):
                fields[name] = value.strip("\"\x27") if value not in ("", "null", "~") else None
        elif section == "urls" and name in ("paper", "page", "documentation"):
            fields[name + "_url"] = value.strip("\"\x27") if value not in ("", "null", "~") else None
    return fields


def dossier_identity(meta):
    keys = set(identities(meta.get("paper_url") or ""))
    for field in ("page_url", "documentation_url"):
        keys.update(identities(meta.get(field) or ""))
    doi = meta.get("doi") or ""
    if doi:
        keys.update(identities("https://doi.org/" + doi))
    raw_arxiv = meta.get("arxiv") or ""
    if raw_arxiv:
        keys.update(identities("https://arxiv.org/abs/" + raw_arxiv))
    versions = set()
    for value in (raw_arxiv, meta.get("paper_url") or ""):
        match = re.search(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(v\d+)(?:\.pdf)?$", value, re.I)
        if match:
            versions.add(match.group(1).lower())
    if any(key.startswith("arxiv:") for key in keys):
        match = re.match(r"^(v\d+)\b", meta.get("version") or "", re.I)
        if match:
            versions.add(match.group(1).lower())
    return sorted(keys), sorted(versions)


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".corpus-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def inventory(source=SOURCE):
    sources = [json.loads(line) for line in (source / "literature/landscape/exports/sources.jsonl").read_text().splitlines() if line.strip()]
    source_index = {}
    for s in sources:
        for key in identities(s.get("canonical_url") or ""):
            source_index.setdefault(key, []).append(s["id"])
    entries = []
    for path in sorted((source / "literature/papers").glob("*.md")):
        data = path.read_bytes()
        meta = frontmatter(data.decode())
        keys, versions = dossier_identity(meta)
        entries.append({"id": meta["id"], "kind": "dossier", "path": str(path.relative_to(source)), "sha256": digest(data), "title": meta.get("title"), "dossier_status": meta.get("status"), "read_status": meta.get("read_status"), "updated": meta.get("updated"), "source_urls": [meta[k] for k in ("paper_url", "page_url", "documentation_url") if meta.get(k)], "arxiv_versions": versions, "identities": keys, "source_ids": sorted({s for k in keys for s in source_index.get(k, [])}), "local_pdf": None, "upload_url": None, "project_id": None, "tag_ids": [], "job_id": None, "paper_id": None, "status": "needs_selection", "note_status": "pending", "error": None})
    for rel in PDFS:
        p = source / rel
        data = p.read_bytes()
        keys = identities("https://arxiv.org/abs/2306.12001v6") if rel.startswith("2306.") else []
        entries.append({"id": "local-pdf:" + rel, "kind": "sprint_report" if rel.endswith("REPORT.pdf") else "literature_pdf", "path": rel, "sha256": digest(data), "identities": keys, "arxiv_versions": ["v6"] if keys else [], "source_ids": sorted({s for k in keys for s in source_index.get(k, [])}), "local_pdf": rel, "upload_url": None, "project_id": None, "tag_ids": [], "job_id": None, "paper_id": None, "status": "needs_selection", "note_status": "not_applicable", "error": None})
    for e in entries:
        e["matching_entry_ids"] = sorted(other["id"] for other in entries if other is not e and set(e["identities"]) & set(other["identities"]))
    return {"version": 1, "source_root_hint": "../ai-safety", "landscape_source_count": len(sources), "idea_count": len(json.loads((source / "literature/landscape/brainstorming/ideas.json").read_text())["ideas"]), "entries": entries}


def validate_origin(base):
    try:
        p = parse.urlsplit(base)
        if (p.scheme != "https" or not p.hostname or p.username is not None or
                p.password is not None or p.path or p.query or p.fragment or
                any(c.isspace() or ord(c) < 32 for c in base)):
            raise ValueError("Expected an HTTPS origin without path, credentials, query or fragment")
        _ = p.port  # Reject invalid ports.
    except ValueError as exc:
        raise ValueError("Expected an HTTPS origin without path, credentials, query or fragment") from exc
    return base


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward session cookies or an upload body on redirects.
        return None


class Api:
    def __init__(self, base, cookie):
        self.base = validate_origin(base)
        self.cookie = cookie
        self.opener = request.build_opener(NoRedirect())

    def call(self, method, path, data=None, content_type="application/json"):
        headers = {"Cookie": "session_token=" + self.cookie, "Accept": "application/json", "User-Agent": "OpenPaperCorpus/1.0"}
        if data is not None:
            headers["Content-Type"] = content_type
        req = request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=120) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except error.HTTPError as exc:
            return exc.code, None  # Do not persist server error bodies or credentials.

    def json(self, method, path, value=None):
        return self.call(method, path, json.dumps(value).encode() if value is not None else None)


def bridge(manifest, origin):
    origin = validate_origin(origin)
    rows = []
    for entry in manifest["entries"]:
        if entry.get("status") != "completed" or not entry.get("paper_id"):
            continue
        paper_id = entry["paper_id"]
        # Avoid turning a malformed, manually entered ID into an arbitrary link.
        import uuid
        paper_id = str(uuid.UUID(paper_id))
        rows.append({"entry_id": entry["id"], "kind": entry["kind"], "source_ids": entry.get("source_ids", []), "identities": entry.get("identities", []), "paper_id": paper_id, "paper_url": origin + "/paper/" + paper_id})
    return {"version": 1, "entries": rows}

def upload(api, entry, source):
    query = "?" + parse.urlencode({"project_id": entry["project_id"]}) if entry.get("project_id") else ""
    if entry.get("local_pdf"):
        p = source / entry["local_pdf"]
        data = p.read_bytes()
        if digest(data) != entry["sha256"]:
            raise ValueError("Local PDF hash changed")
        boundary = "openpaper-" + os.urandom(16).hex()
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{p.name}\"\r\nContent-Type: application/pdf\r\n\r\n".encode() + data + f"\r\n--{boundary}--\r\n".encode())
        return api.call("POST", "/api/paper/upload/" + query, body, "multipart/form-data; boundary=" + boundary)
    return api.json("POST", "/api/paper/upload/from-url/" + query, {"url": entry["upload_url"]})


def step(manifest, entry, api, path, source=SOURCE):
    """One invocation advances a single item; persist before every unsafe request."""
    def persist(): save(path, manifest)
    if entry["status"] == "ready":
        if not entry.get("local_pdf") and not entry.get("upload_url"):
            raise ValueError("Set local_pdf or a verified direct PDF upload_url")
        # Check all aliases, not just the preferred identity. An existing paper must be linked manually.
        for other in manifest["entries"]:
            if other is not entry and set(other.get("identities", [])) & set(entry.get("identities", [])) and (other.get("paper_id") or other.get("job_id") or other.get("status") in ("submitting", "uncertain")):
                raise ValueError("Identity already used or uncertain: " + other["id"])
        entry["status"] = "submitting"
        persist()
        try:
            code, response = upload(api, entry, source)
        except Exception:
            entry["status"] = "uncertain"
            entry["error"] = "Upload response lost; reconcile manually before retry"
            persist()
            raise
        if code == 202 and response and response.get("job_id"):
            entry.update(status="submitted", job_id=response["job_id"], error=None)
        else:
            # Even a server error may occur after creation; never automatically resubmit.
            entry.update(status="uncertain", error=f"Upload returned HTTP {code}; reconcile manually")
        persist()
    if entry["status"] in ("submitting", "uncertain"):
        return
    if entry["status"] == "submitted":
        code, result = api.json("GET", "/api/paper/upload/status/" + parse.quote(entry["job_id"], safe=""))
        if code != 200 or not result:
            entry["error"] = f"Status HTTP {code}; retry polling"
        elif result["status"] == "completed" and result.get("paper_id"):
            entry.update(status="completed", paper_id=result["paper_id"], error=None)
        elif result["status"] in ("failed", "cancelled"):
            entry.update(status=result["status"], error="Upload job ended; inspect in application")
        persist()
    if entry["status"] != "completed":
        return
    paper_id = entry["paper_id"]
    if entry.get("project_id") and not entry.get("project_verified"):
        project_path = "/api/projects/papers/" + parse.quote(entry["project_id"], safe="")
        code, result = api.json("GET", project_path)
        if code != 200 or not isinstance(result, dict):
            entry["error"] = f"Project lookup HTTP {code}"
            persist()
            return
        if not any(p["id"] == paper_id for p in result.get("papers", [])):
            code, _ = api.json("POST", project_path, {"paper_ids": [paper_id]})
            if code != 201:
                entry["error"] = f"Project add HTTP {code}"
                persist()
                return
            # POST can report success even if insertion failed.
            code, result = api.json("GET", project_path)
            if code != 200 or not result or not any(p["id"] == paper_id for p in result.get("papers", [])):
                entry["error"] = "Project membership unverified"
                persist()
                return
        entry["project_verified"] = True
        persist()
    if entry.get("tag_ids") and not entry.get("tags_applied"):
        code, _ = api.json("POST", "/api/paper/tag/bulk", {"paper_ids": [paper_id], "tag_ids": entry["tag_ids"]})
        if code == 200: entry["tags_applied"] = True
        else: entry["error"] = f"Tag HTTP {code}"
        persist()
    # Existing notes are never updated. The database enforces one note per paper.
    if entry["kind"] == "dossier" and entry["note_status"] == "pending":
        q = parse.urlencode({"paper_id": paper_id})
        code, note = api.json("GET", "/api/paper/note?" + q)
        if code == 200:
            entry["note_status"] = "existing_preserved"
        elif code == 404:
            data = (source / entry["path"]).read_bytes()
            if digest(data) != entry["sha256"]: raise ValueError("Dossier hash changed")
            entry["note_status"] = "creating"
            persist()
            try:
                code, _ = api.json("POST", "/api/paper/note?" + q, {"content": data.decode()})
            except Exception:
                entry["note_status"] = "uncertain"
                persist()
                raise
            entry["note_status"] = "created" if code == 201 else "uncertain"
        else:
            entry["error"] = f"Note lookup HTTP {code}"
        persist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "step", "bridge"])
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--id", help="Exact entry ID")
    parser.add_argument("--base-url", help="Authenticated Open Paper origin")
    args = parser.parse_args()
    if args.command == "inventory":
        if args.manifest.exists(): parser.error("Manifest exists; choose a new output path to avoid destroying state")
        m = inventory(args.source)
        save(args.manifest, m)
        print("{} entries; {} sources; {} ideas".format(len(m["entries"]), m["landscape_source_count"], m["idea_count"]))
    elif args.command == "bridge":
        if not args.base_url: parser.error("bridge requires --base-url")
        try:
            print(json.dumps(bridge(json.loads(args.manifest.read_text()), args.base_url), indent=2))
        except ValueError as exc:
            parser.error(str(exc))
    else:
        cookie = os.environ.get("OPENPAPER_SESSION_TOKEN")
        if not args.id or not args.base_url or not cookie: parser.error("step requires --id, --base-url and OPENPAPER_SESSION_TOKEN")
        try: validate_origin(args.base_url)
        except ValueError as exc: parser.error(str(exc))
        m = json.loads(args.manifest.read_text())
        matches = [e for e in m["entries"] if e["id"] == args.id]
        if len(matches) != 1: parser.error("ID must identify exactly one entry")
        step(m, matches[0], Api(args.base_url, cookie), args.manifest, args.source)
        print(matches[0]["status"], matches[0].get("note_status"))


if __name__ == "__main__":
    main()
