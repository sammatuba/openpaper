"""Concurrent-safe, retry-safe append to the user's paper note."""
import hashlib
import uuid

from sqlalchemy import text
from app.database.models import Paper, PaperNote


def note_etag(content: str) -> str:
    return '"' + hashlib.sha256(content.encode("utf-8")).hexdigest() + '"'


def append_note(db, user_id, paper_id: str, request_id: str, content: str):
    paper_id = uuid.UUID(paper_id)
    request_id = uuid.UUID(request_id)
    if not content.strip() or len(content) > 50000:
        raise ValueError("Append must contain 1 to 50000 characters")
    # All MCP append and opt-in note API updates serialize on this paper row.
    paper = db.query(Paper).filter(Paper.id == paper_id, Paper.user_id == user_id).with_for_update().one_or_none()
    if paper is None:
        raise ValueError("Paper not found")
    digest = hashlib.sha256(content.encode()).hexdigest()
    previous = db.execute(text("SELECT paper_id, content_hash FROM mcp_note_requests WHERE user_id=:user_id AND request_id=:request_id"),
                          {"user_id": user_id, "request_id": request_id}).first()
    if previous:
        if previous.paper_id != paper_id or previous.content_hash != digest:
            raise ValueError("Request ID already used for a different append")
        return {"status": "already_applied"}
    note = db.query(PaperNote).filter(PaperNote.paper_id == paper_id).one_or_none()
    if note is not None and note.user_id != user_id:
        raise ValueError("Paper note is not owned by this user")
    if note is None:
        note = PaperNote(paper_id=paper_id, user_id=user_id, content=content)
        db.add(note)
    else:
        note.content = note.content + ("\n\n" if note.content else "") + content
    db.execute(text("INSERT INTO mcp_note_requests (user_id, request_id, paper_id, content_hash) VALUES (:user_id, :request_id, :paper_id, :digest)"),
               {"user_id": user_id, "request_id": request_id, "paper_id": paper_id, "digest": digest})
    db.commit()
    return {"status": "appended"}
