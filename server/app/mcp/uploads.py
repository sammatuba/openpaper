"""Direct MCP PDF imports; claims are durable and never blindly re-enqueued."""
import asyncio
import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.database.models import Paper, PaperUploadJob, ProjectRole
from app.helpers import pdf_download
from app.helpers.parser import validate_pdf_content


DOWNLOAD_TIMEOUT = pdf_download.DOWNLOAD_TIMEOUT


def download_pdf(url: str) -> bytes:
    """Keep the MCP patch point while using the common hard-deadline worker."""
    return pdf_download.download_pdf(url, timeout=DOWNLOAD_TIMEOUT)


def project_write_access(db, user, project_id):
    if project_id is None:
        return None
    project = uuid.UUID(project_id)
    role = db.query(ProjectRole).filter(ProjectRole.project_id == project, ProjectRole.user_id == user.id,
                                       ProjectRole.role.in_(['admin', 'editor'])).first()
    if role is None:
        raise ValueError("Project editor access required")
    return project


def upload_status(db, user, job_id, origin):
    job = db.query(PaperUploadJob).filter(PaperUploadJob.id == uuid.UUID(job_id), PaperUploadJob.user_id == user.id).one_or_none()
    if job is None:
        raise ValueError("Upload job not found")
    paper = db.query(Paper).filter(Paper.upload_job_id == job.id, Paper.user_id == user.id).first()
    complete = job.status == 'completed' and paper is not None
    return {"job_id": str(job.id), "status": job.status, "completed": complete,
            "paper_id": str(paper.id) if paper else None,
            "paper_url": f"{origin}/paper/{paper.id}" if complete else None,
            "error_message": (job.error_message or '')[:1000] if job.status == 'failed' else None,
            "next_action": "Read the imported paper" if complete else
                "Processing failed; inspect the job before another submission" if job.status == 'failed' else
                "Poll this job ID; never resubmit to restart an uncertain or stalled job"}


async def import_pdf(db, user, origin, url, project_id=None):
    # Lazy imports avoid initializing processing/storage in retrieval-only tests.
    from app.api.paper_upload_api import check_subscription_limits, upload_raw_file_microservice
    from app.mcp.research_import import _lock_import_admissions, _check_upload_capacity
    project = project_write_access(db, user, project_id)
    data = await asyncio.to_thread(download_pdf, url)
    valid, error = await validate_pdf_content(data, 'MCP import')
    if not valid:
        raise ValueError(error)
    digest = hashlib.sha256(data).hexdigest()
    # A content+user+destination identity survives signed URL changes and retries.
    job_id = uuid.uuid5(uuid.NAMESPACE_URL, f"openpaper:mcp:pdf:v1:{user.id}:{project}:{digest}")
    # Share the deployed URL importer's admission lock and occupancy count so
    # attachment uploads cannot race pending imports for the user's last slot.
    _lock_import_admissions(db, user)
    project_write_access(db, user, project_id)  # Access may change during retrieval.
    existing = db.query(PaperUploadJob).filter(PaperUploadJob.id == job_id, PaperUploadJob.user_id == user.id).first()
    if existing:
        return {**upload_status(db, user, str(job_id), origin), "reused": True}
    _check_upload_capacity(db, user)
    error = await check_subscription_limits(user, db, str(project) if project else None)
    if error:
        raise ValueError(error)
    job = PaperUploadJob(id=job_id, user_id=user.id, status='pending', started_at=datetime.now(timezone.utc))
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Only a matching existing claim is a duplicate; other DB errors propagate.
        return {**upload_status(db, user, str(job_id), origin), "reused": True}
    # Durable claim precedes side effects. If this call dies, retries report the
    # claim for reconciliation and do not repeat storage or expensive processing.
    await upload_raw_file_microservice(data, 'Imported paper.pdf', job, user, db, project,
                                      preserve_on_dispatch_error=True)
    db.expire_all()
    return {**upload_status(db, user, str(job_id), origin), "reused": False}
