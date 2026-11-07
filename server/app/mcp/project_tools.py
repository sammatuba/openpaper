"""Authenticated MCP project operations. Actor identity comes only from OAuth."""
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.database.models import Paper, Project, ProjectPaper, ProjectRole, ProjectRoles
from app.helpers.subscription_limits import can_user_add_papers_to_project, can_user_create_project


def _uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"Invalid {label}") from exc


def _title(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
        raise ValueError("Project title must contain 1 to 200 characters")
    return value.strip()


def _description(value: str | None) -> str | None:
    if value is not None and (not isinstance(value, str) or len(value) > 10000):
        raise ValueError("Project description must contain at most 10000 characters")
    return value


def _role(db, user, project_id: uuid.UUID, allowed=None):
    role = (
        db.query(ProjectRole)
        .filter(ProjectRole.project_id == project_id, ProjectRole.user_id == user.id)
        .one_or_none()
    )
    if role is None:
        raise ValueError("Project not found or not accessible")
    if allowed is not None and role.role not in allowed:
        raise PermissionError("Insufficient project permissions")
    return role


def _project_result(project, public_origin: str, status: str) -> dict:
    return {
        "status": status,
        "id": str(project.id),
        "title": project.title,
        "description": project.description,
        "url": f"{public_origin.rstrip('/')}/projects/{project.id}",
    }


def create_project(db, user, title: str, request_id: str, description: str | None,
                   public_origin: str) -> dict:
    """Create once for a user/request UUID; reject a changed payload on replay."""
    title = _title(title)
    description = _description(description)
    request_uuid = _uuid(request_id, "request_id")
    project_id = uuid.uuid5(uuid.NAMESPACE_URL, f"openpaper:mcp:project:{user.id}:{request_uuid}")

    def previous():
        row = db.query(Project).filter(Project.id == project_id).one_or_none()
        if row is None:
            return None
        if row.admin_id != user.id or row.title != title or row.description != description:
            raise ValueError("Request ID already used for different project creation")
        return _project_result(row, public_origin, "already_created")

    existing = previous()
    if existing is not None:
        return existing

    permitted, reason = can_user_create_project(db, user)
    if not permitted:
        raise PermissionError(reason or "Project creation limit reached")
    row = Project(id=project_id, admin_id=user.id, title=title, description=description)
    db.add(row)
    db.add(ProjectRole(project_id=project_id, user_id=user.id, role=ProjectRoles.ADMIN))
    try:
        db.commit()  # Project and admin membership are one transaction.
    except IntegrityError:
        db.rollback()
        existing = previous()  # Concurrent identical request.
        if existing is not None:
            return existing
        raise
    db.refresh(row)
    return _project_result(row, public_origin, "created")


def update_project(db, user, project_id: str, public_origin: str,
                   title: str | None = None, description: str | None = None,
                   clear_description: bool = False) -> dict:
    pid = _uuid(project_id, "project_id")
    if clear_description and description is not None:
        raise ValueError("Cannot set and clear the description simultaneously")
    if title is None and description is None and not clear_description:
        raise ValueError("Specify at least one field to update")
    if title is not None:
        title = _title(title)
    description = _description(description)
    _role(db, user, pid, {ProjectRoles.ADMIN})
    row = db.query(Project).filter(Project.id == pid).one_or_none()
    if row is None:
        raise ValueError("Project not found or not accessible")
    if title is not None:
        row.title = title
    if clear_description:
        row.description = None
    elif description is not None:
        row.description = description
    db.commit()
    db.refresh(row)
    return _project_result(row, public_origin, "updated")


def add_paper_to_project(db, user, project_id: str, paper_id: str) -> dict:
    pid, paper_uuid = _uuid(project_id, "project_id"), _uuid(paper_id, "paper_id")
    _role(db, user, pid, {ProjectRoles.ADMIN, ProjectRoles.EDITOR})
    project = db.query(Project).filter(Project.id == pid).with_for_update().one_or_none()
    if project is None:
        raise ValueError("Project not found or not accessible")
    paper = db.query(Paper).filter(Paper.id == paper_uuid, Paper.user_id == user.id).one_or_none()
    if paper is None:
        raise ValueError("Paper not found or not owned by the current user")
    prior = db.query(ProjectPaper).filter(
        ProjectPaper.project_id == pid, ProjectPaper.paper_id == paper_uuid
    ).one_or_none()
    if prior is not None:
        return {"status": "already_present", "project_id": str(pid), "paper_id": str(paper_uuid)}
    permitted, reason = can_user_add_papers_to_project(db, user, project_id=pid, paper_count=1)
    if not permitted:
        raise PermissionError(reason or "Project paper limit reached")
    db.add(ProjectPaper(project_id=pid, paper_id=paper_uuid))
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "added", "project_id": str(pid), "paper_id": str(paper_uuid)}


def remove_paper_from_project(db, user, project_id: str, paper_id: str) -> dict:
    pid, paper_uuid = _uuid(project_id, "project_id"), _uuid(paper_id, "paper_id")
    _role(db, user, pid, {ProjectRoles.ADMIN, ProjectRoles.EDITOR})
    project = db.query(Project).filter(Project.id == pid).with_for_update().one_or_none()
    if project is None:
        raise ValueError("Project not found or not accessible")
    link = db.query(ProjectPaper).filter(
        ProjectPaper.project_id == pid, ProjectPaper.paper_id == paper_uuid
    ).one_or_none()
    if link is None:
        return {"status": "not_present", "project_id": str(pid), "paper_id": str(paper_uuid)}
    db.delete(link)  # Never delete the underlying paper or its annotations.
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "removed", "project_id": str(pid), "paper_id": str(paper_uuid)}


def list_project_papers(db, user, project_id: str, public_origin: str,
                        offset: int = 0, limit: int = 50) -> dict:
    pid = _uuid(project_id, "project_id")
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid offset or limit")
    _role(db, user, pid)
    rows = (
        db.query(Paper)
        .join(ProjectPaper, ProjectPaper.paper_id == Paper.id)
        .filter(ProjectPaper.project_id == pid)
        .order_by(Paper.created_at.desc(), Paper.id)
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    return {
        "project_id": str(pid),
        "papers": [
            {"id": str(p.id), "title": p.title, "authors": p.authors,
             "abstract": p.abstract, "is_owner": p.user_id == user.id,
             "url": f"{public_origin.rstrip('/')}/paper/{p.id}"}
            for p in rows[:limit]
        ],
        "next_offset": offset + limit if len(rows) > limit else None,
    }
