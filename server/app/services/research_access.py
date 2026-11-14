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
    if lock: query = query.with_for_update()
    project = query.first()
    if not project: raise HTTPException(404, "Project not found")
    roles = db.query(ProjectRole).filter(ProjectRole.project_id == project_id, ProjectRole.user_id == actor_id)
    if lock: roles = roles.with_for_update()
    role = roles.first()
    if project.admin_id != actor_id and role is None: raise HTTPException(404, "Project not found")
    if write and project.admin_id != actor_id and role.role not in ("admin", "editor"):
        raise HTTPException(403, "Editing requires an editor role")
    return project


def advance_change_sequence(db, project_id):
    """Every committed research mutation advances the project's monotonic change
    sequence inside its own transaction (contract 1). The root row is created on the
    first research mutation and stays v1 until conversion flips the generation."""
    from app.database.models import ResearchProject
    row = db.query(ResearchProject).filter(ResearchProject.project_id == project_id).with_for_update().first()
    if row is None:
        row = ResearchProject(project_id=project_id, storage_generation="v1", change_sequence=0)
        db.add(row); db.flush()
    row.change_sequence = (row.change_sequence or 0) + 1
    return row.change_sequence
