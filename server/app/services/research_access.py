"""Shared research authorization — one semantic for every new research service.

Owner (project.admin_id) passes read and write without a membership row; membership
roles admin/editor pass write; viewer is read-only; non-members and missing projects
are indistinguishable 404s. Mirrors the deployed v1 investigation semantics
(app/services/investigation.py access()). Permissions are re-checked inside each
mutation transaction by the callers.
"""
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.database.models import Project, ProjectRole


def authorize(db: Session, project_id, actor_id, *, write=False, lock=False):
    query = db.query(Project).filter(Project.id == project_id)
    # Lock order is project row first, research root second, for every research writer. Conversion
    # and the legacy save take the project row FOR UPDATE (lock=True) before the root. Every other
    # writer takes it FOR KEY SHARE here: the same lock its foreign-key inserts need later, taken
    # before it can hold the root, so it queues behind a conversion instead of deadlocking with it.
    if lock: query = query.with_for_update()
    elif write: query = query.with_for_update(read=True, key_share=True)
    project = query.first()
    if not project: raise HTTPException(404, "Project not found")
    roles = db.query(ProjectRole).filter(ProjectRole.project_id == project_id, ProjectRole.user_id == actor_id)
    if lock: roles = roles.with_for_update()
    role = roles.first()
    # Committed ownership/membership state, even when this session cached the rows:
    # a demotion committed by another session must be observed here (R37).
    db.refresh(project)
    if role is not None: db.refresh(role)
    if project.admin_id != actor_id and role is None: raise HTTPException(404, "Project not found")
    if write and project.admin_id != actor_id and role.role not in ("admin", "editor"):
        raise HTTPException(403, "Editing requires an editor role")
    return project


def lock_project(db, project_id):
    """Serialize research writers that must read project-wide state before writing: take the
    project root row lock for the rest of the transaction, creating the root first so the very
    first writer has a row to lock. Call it after authorize(write=True), which already holds the
    project row lock that orders this writer against conversion and the legacy save."""
    from sqlalchemy import text
    parameters = {"p": str(project_id)}
    db.execute(text("INSERT INTO research_projects (project_id, storage_generation, change_sequence) "
                    "VALUES (:p, 'v1', 0) ON CONFLICT (project_id) DO NOTHING"), parameters)
    db.execute(text("SELECT 1 FROM research_projects WHERE project_id = :p FOR UPDATE"), parameters)


def advance_change_sequence(db, project_id):
    """Every committed research mutation advances the project's monotonic change
    sequence inside its own transaction (contract 1). The increment is a single
    atomic UPDATE ... RETURNING, so cached ORM instances cannot lose increments and
    concurrent first mutations initialize safely (R28). The root row stays v1 until
    conversion flips the generation."""
    from sqlalchemy import text
    parameters = {"p": str(project_id)}
    drawn = db.execute(text("UPDATE research_projects SET change_sequence = change_sequence + 1 "
                            "WHERE project_id = :p RETURNING change_sequence"), parameters).scalar()
    if drawn is None:
        # First research mutation: initialize the root; a racing initializer wins the
        # insert and this session's UPDATE then draws the next value.
        db.execute(text("INSERT INTO research_projects (project_id, storage_generation, change_sequence) "
                        "VALUES (:p, 'v1', 0) ON CONFLICT (project_id) DO NOTHING"), parameters)
        drawn = db.execute(text("UPDATE research_projects SET change_sequence = change_sequence + 1 "
                                "WHERE project_id = :p RETURNING change_sequence"), parameters).scalar_one()
    return int(drawn)
