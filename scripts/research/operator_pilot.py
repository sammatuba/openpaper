#!/usr/bin/env python3
"""Owner-only, explicitly authorized three-item corpus pilot.

This administrative maintenance tool creates a short-lived application session
in the existing database. It never prints or writes its credentials. Running it
requires separate operator authorization; preparing it does not run a pilot.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import uuid

import corpus

OWNER = "jansammat26@gmail.com"
ORIGIN = "https://papers.jansammat26.workers.dev"
AGENT = "operator-corpus-pilot"


def select_entries(manifest, ids, source):
    if not 1 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        raise ValueError("Select one to three distinct IDs")
    entries = manifest.get("entries", [])
    selected = []
    source = Path(source).resolve()
    for entry_id in ids:
        matches = [e for e in entries if e.get("id") == entry_id]
        if len(matches) != 1:
            raise ValueError("Each ID must identify exactly one manifest entry")
        e = matches[0]
        if e.get("status") not in ("ready", "submitted", "completed"):
            raise ValueError("Each entry must be manually selected or resumable")
        if e.get("note_status") in ("creating", "uncertain"):
            raise ValueError("An uncertain note requires manual reconciliation")
        if e["status"] == "submitted" and not e.get("job_id"):
            raise ValueError("Submitted entries require a job ID")
        if e["status"] == "completed" and not e.get("paper_id"):
            raise ValueError("Completed entries require a paper ID")
        rel = e.get("local_pdf") if e["status"] == "ready" else None
        if e["status"] == "ready" and not (rel or e.get("upload_url")):
            raise ValueError("Ready entries require a selected PDF")
        if e.get("kind") == "dossier" and e.get("note_status") == "pending" and e["status"] == "completed":
            rel = e.get("path")
        if rel:
            path = (source / rel).resolve()
            if not path.is_relative_to(source) or not path.is_file() or corpus.digest(path.read_bytes()) != e.get("sha256"):
                raise ValueError("Selected source file is missing, outside source, or changed")
        if e["status"] == "ready":
            for other in entries:
                if other is not e and set(e.get("identities", [])) & set(other.get("identities", [])) and (other.get("paper_id") or other.get("job_id") or other.get("status") in ("submitting", "uncertain")):
                    raise ValueError("Identity requires manual reconciliation")
        selected.append(e)
    # Two selected entries with the same identity would race after the first
    # submission. Reject before making a session or issuing any request.
    for index, e in enumerate(selected):
        if e["status"] == "ready" and any(set(e.get("identities", [])) & set(other.get("identities", [])) for other in selected[index + 1:]):
            raise ValueError("Selected entries share an identity")
    return selected


def database_url():
    result = subprocess.run(
        ["gcloud", "--configuration=personal", "--project=openpaper-sammatuba", "secrets", "versions", "access", "latest", "--secret=DATABASE_URL"],
        capture_output=True, check=False, text=True,
    )
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("Could not retrieve the database credential")
    return result.stdout.strip()


def load_models(url):
    # Both python-dotenv and pydantic's env_file setting must be disabled.
    # An empty working directory prevents the latter from reading .env.
    old_dir = os.getcwd()
    previous_url = os.environ.get("DATABASE_URL")
    previous_disable = os.environ.get("PYTHON_DOTENV_DISABLED")
    sys.path.insert(0, str(corpus.ROOT / "server"))
    try:
        os.environ["DATABASE_URL"] = url
        os.environ["PYTHON_DOTENV_DISABLED"] = "true"
        with tempfile.TemporaryDirectory(prefix="openpaper-pilot-") as empty:
            os.chdir(empty)
            from app.database.database import engine
            from app.database.models import Session as AppSession, User
            from sqlalchemy.orm import sessionmaker
            return sessionmaker(bind=engine), User, AppSession
    finally:
        os.chdir(old_dir)
        for key, value in (("DATABASE_URL", previous_url), ("PYTHON_DOTENV_DISABLED", previous_disable)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def owner_session(session_factory, user_model, session_model):
    db = session_factory()
    token = None
    try:
        owner = db.query(user_model).filter(user_model.email == OWNER).one_or_none()
        if not owner or owner.email != OWNER or not owner.is_active or not owner.is_email_verified or owner.is_blocked:
            raise ValueError("The configured owner is missing or not eligible")
        token = secrets.token_hex(32)
        record = session_model(id=uuid.uuid4(), user_id=owner.id, token=token,
                               expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                               user_agent=AGENT)
        db.add(record)
        db.commit()
        yield token
    finally:
        try:
            db.close()
        finally:
            if token is not None:
                # A separate connection also handles an ambiguous failed commit.
                cleanup = session_factory()
                try:
                    cleanup.query(session_model).filter(session_model.token == token).delete(synchronize_session=False)
                    cleanup.commit()
                finally:
                    cleanup.close()


def run_pilot(manifest, ids, path, source, session_factory, user_model, session_model):
    selected = select_entries(manifest, ids, source)
    with owner_session(session_factory, user_model, session_model) as token:
        api = corpus.Api(ORIGIN, token)
        for entry in selected:
            corpus.step(manifest, entry, api, path, source)
            print(entry["id"], entry["status"], entry.get("note_status"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-three-item-pilot", action="store_true", required=True)
    parser.add_argument("--id", action="append", required=True, help="Explicit manifest ID; repeat at most three times")
    parser.add_argument("--manifest", type=Path, default=corpus.MANIFEST)
    parser.add_argument("--source", type=Path, default=corpus.SOURCE)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        select_entries(manifest, args.id, args.source)
        factory, user_model, session_model = load_models(database_url())
        run_pilot(manifest, args.id, args.manifest, args.source, factory, user_model, session_model)
    except Exception:
        # Database and HTTP exceptions can contain credentials. Never echo them.
        print("Pilot stopped; inspect manifest state and reconcile before retrying.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
