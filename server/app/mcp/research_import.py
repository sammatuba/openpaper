"""Authenticated, idempotent research PDF import via existing upload/job pipeline."""
import uuid
import re
from datetime import datetime, timezone

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.database.models import (
    JobStatus, MCPPaperImportRequest, Paper, PaperUploadJob, Project,
    ProjectPaper, ProjectRole, ProjectRoles, User,
)
from app.helpers.pdf_jobs import jobs_client
from app.helpers.paper_search import normalize_doi
from app.helpers.subscription_limits import (
    can_user_access_knowledge_base, can_user_add_papers_to_project,
    get_user_subscription_plan, get_plan_limits, PAPER_UPLOAD_KEY,
)
from app.mcp.research_url import fetch_research_pdf, normalize_research_pdf_url


def _uuid(value: str, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid {name}") from exc


def _require_editor(db, user, pid: uuid.UUID) -> None:
    role = db.query(ProjectRole).filter(
        ProjectRole.project_id == pid, ProjectRole.user_id == user.id
    ).one_or_none()
    if role is None or role.role not in (ProjectRoles.ADMIN, ProjectRoles.EDITOR):
        raise PermissionError("Project not found or import permission denied")


def _summary(db, row) -> dict:
    job_status = None
    if row.upload_job_id:
        job = db.query(PaperUploadJob).filter(
            PaperUploadJob.id == row.upload_job_id,
            PaperUploadJob.user_id == row.user_id,
        ).one_or_none()
        job_status = (getattr(job.status, "value", job.status) if job is not None else "missing")
    paper_id = row.paper_id
    if paper_id is None and row.upload_job_id:
        paper = db.query(Paper).filter(
            Paper.upload_job_id == row.upload_job_id,
            Paper.user_id == row.user_id,
        ).one_or_none()
        paper_id = paper.id if paper is not None else None
    return {
        "request_id": str(row.request_id),
        "project_id": str(row.project_id),
        "source_url": row.source_url,
        "status": row.status,
        "upload_job_id": str(row.upload_job_id) if row.upload_job_id else None,
        "paper_id": str(paper_id) if paper_id else None,
        "processing_status": job_status,
        "error": row.error_message,
    }


def get_import_status(db, user, request_id: str) -> dict:
    rid = _uuid(request_id, "request_id")
    row = db.query(MCPPaperImportRequest).filter(
        MCPPaperImportRequest.request_id == rid,
        MCPPaperImportRequest.user_id == user.id,
    ).one_or_none()
    if row is None:
        raise ValueError("Import request not found")
    _require_editor(db, user, row.project_id)
    return _summary(db, row)


def _owned_arxiv_match(db, user, source_key: str):
    if not source_key.startswith("arxiv:"):
        return None
    identifier = source_key.removeprefix("arxiv:")
    base = re.sub(r"v[0-9]+$", "", identifier)
    suffix = f"arxiv.{base}"
    candidates = db.query(Paper).filter(
        Paper.user_id == user.id,
        func.lower(Paper.doi).contains(suffix, autoescape=True),
    ).all()
    expected = "10.48550/arxiv." + identifier
    pattern = re.escape(expected) + (r"(?:v[0-9]+)?" if identifier == base else "")
    return next((paper for paper in candidates
                 if re.fullmatch(pattern, normalize_doi(paper.doi) or "")), None)


def _check_limit(db, user, func_check, *args, **kwargs):
    ok, reason = func_check(db, user, *args, **kwargs)
    if not ok:
        raise PermissionError(reason or "Subscription limit reached")


def _lock_import_admissions(db, user):
    # Held only through the durable reservation/job commit, never remote I/O.
    if db.query(User.id).filter(User.id == user.id).with_for_update().one_or_none() is None:
        raise PermissionError("User not found")


def _check_upload_capacity(db, user, exclude_request=None):
    limit = get_plan_limits(get_user_subscription_plan(db, user))[PAPER_UPLOAD_KEY]
    if limit == float("inf"):
        return
    completed = select(func.count(Paper.id)).outerjoin(
        PaperUploadJob, PaperUploadJob.id == Paper.upload_job_id
    ).where(Paper.user_id == user.id, or_(
        Paper.upload_job_id.is_(None), PaperUploadJob.status == JobStatus.COMPLETED
    ))
    ambiguous = exists().where(
        MCPPaperImportRequest.user_id == user.id,
        MCPPaperImportRequest.upload_job_id == PaperUploadJob.id,
        MCPPaperImportRequest.status.in_(("submitting", "submitted", "needs_reconciliation")),
    )
    outstanding = select(func.count(PaperUploadJob.id)).where(
        PaperUploadJob.user_id == user.id,
        or_(PaperUploadJob.status.notin_((JobStatus.COMPLETED, JobStatus.FAILED)),
            and_(PaperUploadJob.status != JobStatus.COMPLETED, ambiguous)),
    )
    unbacked = select(func.count()).select_from(MCPPaperImportRequest).where(
        MCPPaperImportRequest.user_id == user.id,
        MCPPaperImportRequest.status.notin_(("failed", "linked_existing")),
        ~exists().where(PaperUploadJob.id == MCPPaperImportRequest.upload_job_id,
                        PaperUploadJob.user_id == user.id),
    )
    if exclude_request is not None:
        unbacked = unbacked.where(MCPPaperImportRequest.request_id != exclude_request)
    # One SQL snapshot avoids a completion between separate count queries
    # disappearing from both completed and pending occupancy.
    occupied = db.execute(select(completed.scalar_subquery()
                                 + outstanding.scalar_subquery()
                                 + unbacked.scalar_subquery())).scalar_one()
    if occupied >= limit:
        raise PermissionError("Paper upload limit reached, including outstanding imports")


async def import_paper_from_url(db, user, project_id: str, request_id: str, url: str) -> dict:
    """Start at most one ingestion for a project/source; expose job status separately.

    A reserved request is never auto-reissued after an ambiguous process crash.
    The operator must reconcile the job first, avoiding duplicate paid processing.
    """
    pid, rid = _uuid(project_id, "project_id"), _uuid(request_id, "request_id")
    source_key, pdf_url = normalize_research_pdf_url(url)
    _require_editor(db, user, pid)
    _lock_import_admissions(db, user)

    # The project lock serializes same-project admissions and paper-count quotas.
    project = db.query(Project).filter(Project.id == pid).with_for_update().one_or_none()
    if project is None:
        raise ValueError("Project not found or import permission denied")
    _require_editor(db, user, pid)
    existing_request = db.query(MCPPaperImportRequest).filter(
        MCPPaperImportRequest.user_id == user.id,
        MCPPaperImportRequest.request_id == rid,
    ).one_or_none()
    if existing_request is not None:
        if (existing_request.project_id != pid or existing_request.source_key != source_key
                or existing_request.source_url != url):
            raise ValueError("Request ID already used for a different import")
        result = _summary(db, existing_request)
        result["replay"] = True
        db.rollback()
        return result
    existing_source = db.query(MCPPaperImportRequest).filter(
        MCPPaperImportRequest.user_id == user.id,
        MCPPaperImportRequest.project_id == pid,
        MCPPaperImportRequest.source_key == source_key,
    ).one_or_none()
    if existing_source is not None:
        result = _summary(db, existing_source)
        result["status"] = "already_requested"
        db.rollback()
        return result

    # Link existing owned arXiv papers instead of paying for duplicate ingestion.
    owned = _owned_arxiv_match(db, user, source_key)
    if owned is not None:
        link = db.query(ProjectPaper).filter(
            ProjectPaper.project_id == pid, ProjectPaper.paper_id == owned.id
        ).one_or_none()
        if link is None:
            _check_limit(db, user, can_user_add_papers_to_project, pid, paper_count=1)
            db.add(ProjectPaper(project_id=pid, paper_id=owned.id))
        row = MCPPaperImportRequest(
            user_id=user.id, request_id=rid, project_id=pid,
            source_key=source_key, source_url=url, status="linked_existing",
            paper_id=owned.id,
        )
        db.add(row)
        db.commit()
        return {**_summary(db, row), "replay": False}

    _check_upload_capacity(db, user)
    _check_limit(db, user, can_user_access_knowledge_base)
    _check_limit(db, user, can_user_add_papers_to_project, pid, paper_count=1)
    row = MCPPaperImportRequest(
        user_id=user.id, request_id=rid, project_id=pid,
        source_key=source_key, source_url=url, status="reserved",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another request won the unique source key race; never start a second job.
        existing = db.query(MCPPaperImportRequest).filter(
            MCPPaperImportRequest.user_id == user.id,
            MCPPaperImportRequest.project_id == pid,
            MCPPaperImportRequest.source_key == source_key,
        ).one_or_none()
        if existing is None:
            raise
        result = _summary(db, existing)
        result["status"] = "already_requested"
        return result

    try:
        data = await fetch_research_pdf(pdf_url)
        # Membership can change during remote retrieval.
        _lock_import_admissions(db, user)
        _require_editor(db, user, pid)
        _check_upload_capacity(db, user, exclude_request=rid)
        _check_limit(db, user, can_user_access_knowledge_base)
        job = PaperUploadJob(
            user_id=user.id, status=JobStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.flush()
        row.upload_job_id = job.id
        row.status = "submitting"
        db.commit()
        filename = source_key.replace(":", "-").replace("/", "-") + ".pdf"
        task_id = await jobs_client.submit_pdf_processing_job_with_upload(
            pdf_bytes=data, paper_upload_job=job, db=db, user=user,
            project_id=pid, original_filename=filename,
            preserve_on_dispatch_error=True,
        )
        job.task_id = task_id
        row.status = "submitted"
        db.commit()
        result = _summary(db, row)
        result["replay"] = False
        return result
    except Exception as exc:
        db.rollback()
        row = db.query(MCPPaperImportRequest).filter(
            MCPPaperImportRequest.user_id == user.id,
            MCPPaperImportRequest.request_id == rid,
        ).one()
        # A task may already have been dispatched. Never assert that it failed
        # or schedule a second task merely because the MCP request failed.
        # The operator must reconcile the durable upload_job_id and its state.
        row.status = "needs_reconciliation" if row.upload_job_id else "failed"
        row.error_message = type(exc).__name__  # No secrets or untrusted exception text.
        db.commit()
        return {**_summary(db, row), "replay": False}
