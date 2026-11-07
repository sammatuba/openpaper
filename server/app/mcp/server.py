"""Opt-in authenticated MCP server; all tools derive identity from OAuth."""
import os

from cryptography.fernet import Fernet
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token
from key_value.aio.stores.postgresql import PostgreSQLStore
from key_value.aio.wrappers.encryption.fernet import FernetEncryptionWrapper
from sqlalchemy import func, or_

from app.database.database import SessionLocal
from app.database.models import Annotation, Paper, PaperNote, Project, ProjectRole, User
from app.mcp.notes import append_note
from app.mcp import project_tools
from app.helpers.paper_search import normalize_doi


def create_mcp_app():
    public_origin = os.environ["CLIENT_DOMAIN"].rstrip("/")
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    storage = FernetEncryptionWrapper(
        PostgreSQLStore(url=os.environ["DATABASE_URL"], table_name="mcp_oauth_store", auto_create=False),
        fernet=Fernet(os.environ["MCP_STORAGE_ENCRYPTION_KEY"].encode()),
    )
    auth = GoogleProvider(client_id=client_id, client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        base_url=public_origin, redirect_path="/api/mcp/auth/callback",
        required_scopes=["openid", "email"], client_storage=storage,
        jwt_signing_key=os.environ["MCP_JWT_SIGNING_KEY"], forward_resource=False)
    mcp = FastMCP("Open Paper", auth=auth)

    def current_user(db):
        token = get_access_token()
        claims = token.claims if token else {}
        verified = claims.get("email_verified")
        email = claims.get("email")
        if not email or verified not in (True, "true") or claims.get("aud") != client_id:
            raise ValueError("Verified Google identity required")
        allowed = {e.strip().lower() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()}
        if allowed and email.lower() not in allowed:
            raise ValueError("Identity is not allowed")
        user = db.query(User).filter(func.lower(User.email) == email.lower(), User.is_active.is_(True), User.is_blocked.is_(False)).one_or_none()
        if user is None:
            raise ValueError("User not found")
        return user

    def get_owned(db, user, paper_id):
        paper = db.query(Paper).filter(Paper.id == paper_id, Paper.user_id == user.id).one_or_none()
        if paper is None:
            raise ValueError("Paper not found")
        return paper

    def paper_dict(p):
        return {"id": str(p.id), "title": p.title, "authors": p.authors, "abstract": p.abstract,
                "doi": p.doi, "source_url": f"https://doi.org/{normalize_doi(p.doi)}" if normalize_doi(p.doi) else None, "url": f"{public_origin}/paper/{p.id}"}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def search_papers(query: str, limit: int = 20) -> list[dict]:
        """Search your own paper titles and abstracts."""
        if not query.strip() or len(query) > 200 or not 1 <= limit <= 50:
            raise ValueError("Invalid query or limit")
        with SessionLocal() as db:
            user = current_user(db)
            needle = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            papers = db.query(Paper).filter(Paper.user_id == user.id, or_(Paper.title.ilike(needle, escape="\\"), Paper.abstract.ilike(needle, escape="\\"))).limit(limit).all()
            return [paper_dict(p) for p in papers]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def get_paper(paper_id: str) -> dict:
        """Get metadata for one of your papers."""
        with SessionLocal() as db:
            return paper_dict(get_owned(db, current_user(db), paper_id))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def read_paper_text(paper_id: str, offset: int = 0, limit: int = 12000) -> dict:
        """Read a bounded character range of the extracted paper text for citation grounding."""
        if offset < 0 or not 1 <= limit <= 20000:
            raise ValueError("Invalid offset or limit")
        with SessionLocal() as db:
            paper = get_owned(db, current_user(db), paper_id)
            text = paper.raw_content or ""
            return {"paper_id": str(paper.id), "offset": offset, "text": text[offset:offset + limit],
                    "next_offset": min(offset + limit, len(text)), "total_characters": len(text),
                    "page_offset_map": paper.page_offset_map, "source_url": f"https://doi.org/{normalize_doi(paper.doi)}" if normalize_doi(paper.doi) else None}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def list_projects() -> list[dict]:
        """List projects accessible to the authenticated user."""
        with SessionLocal() as db:
            user = current_user(db)
            rows = db.query(Project).outerjoin(ProjectRole, ProjectRole.project_id == Project.id).filter(or_(Project.admin_id == user.id, ProjectRole.user_id == user.id)).distinct().limit(100).all()
            return [{"id": str(p.id), "title": p.title, "description": p.description} for p in rows]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def create_project(title: str, request_id: str, description: str | None = None) -> dict:
        """Create a research project. Supply a fresh UUID request_id; reuse it for retries."""
        with SessionLocal() as db:
            return project_tools.create_project(
                db, current_user(db), title, request_id, description, public_origin
            )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def update_project(project_id: str, title: str | None = None,
                       description: str | None = None,
                       clear_description: bool = False) -> dict:
        """Update a project you administer; omit fields to preserve existing values."""
        with SessionLocal() as db:
            return project_tools.update_project(
                db, current_user(db), project_id, public_origin,
                title=title, description=description,
                clear_description=clear_description,
            )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def add_paper_to_project(project_id: str, paper_id: str) -> dict:
        """Add one of your own papers to a project where you can edit."""
        with SessionLocal() as db:
            return project_tools.add_paper_to_project(
                db, current_user(db), project_id, paper_id
            )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def remove_paper_from_project(project_id: str, paper_id: str) -> dict:
        """Unlink a paper from a project; do not delete the underlying library paper."""
        with SessionLocal() as db:
            return project_tools.remove_paper_from_project(
                db, current_user(db), project_id, paper_id
            )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def list_project_papers(project_id: str, offset: int = 0, limit: int = 50) -> dict:
        """List paper metadata in an accessible project, with pagination."""
        with SessionLocal() as db:
            return project_tools.list_project_papers(
                db, current_user(db), project_id, public_origin,
                offset=offset, limit=limit,
            )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def get_paper_note(paper_id: str) -> dict:
        """Read your paper note."""
        with SessionLocal() as db:
            user = current_user(db)
            get_owned(db, user, paper_id)
            note = db.query(PaperNote).filter(PaperNote.paper_id == paper_id, PaperNote.user_id == user.id).one_or_none()
            return {"content": note.content if note else None}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    def list_annotations(paper_id: str) -> list[dict]:
        """List your annotations for a paper."""
        with SessionLocal() as db:
            user = current_user(db)
            get_owned(db, user, paper_id)
            rows = db.query(Annotation).filter(Annotation.paper_id == paper_id, Annotation.user_id == user.id).limit(200).all()
            return [{"id": str(a.id), "content": a.content, "role": a.role} for a in rows]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def append_paper_note(paper_id: str, request_id: str, content: str) -> dict:
        """Append explicitly chosen content to a paper note. Reuse a UUID request_id on retry."""
        with SessionLocal() as db:
            user = current_user(db)
            return append_note(db, user.id, paper_id, request_id, content)

    return mcp.http_app(path="/api/mcp", stateless_http=True)
