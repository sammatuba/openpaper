"""
FastAPI application for the Celery PDF processing service.
Provides endpoints for submitting tasks and checking status.
"""
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import os

from src.celery_app import celery_app
# Register the tasks /tasks/run executes. Celery's include= only loads them at
# worker boot, and under Cloud Tasks this process is uvicorn alone.
import src.tasks  # noqa: F401,E402
from src.logging_config import configure_logging

# Configure logging
configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PDF Processing Service",
    description="Celery-based service for processing PDF files",
    version="1.0.0"
)


class TaskSubmission(BaseModel):
    pdf_base64: str
    webhook_url: str
    processing_options: Optional[Dict[str, Any]] = {}


class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    progress_message: Optional[str] = None  # Human-readable progress message


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "pdf-processing"}


class RunTaskRequest(BaseModel):
    task: str
    task_id: str
    kwargs: Dict[str, Any] = {}


# The tasks Cloud Tasks may push. health_check is excluded because its body
# inspects worker state that does not exist in this mode.
RUNNABLE_TASKS = frozenset(
    {
        "upload_and_process_file",
        "process_data_table",
        "periodic_zotero_sync",
        "delayed_referral_settlement_callback",
    }
)


@app.post("/tasks/run")
def run_task(
    request: RunTaskRequest,
    authorization: Optional[str] = Header(default=None),
    x_jobs_secret: Optional[str] = Header(default=None),
):
    """
    Execute one Celery task in this process (TASK_BACKEND=cloudtasks).

    Cloud Tasks pushes here instead of a broker delivering to a worker. The
    task runs with Celery's eager `apply`, so `self.request.id` is the id the
    server stored on the job and `update_state` works against the memory
    result backend. The task reports its own outcome to the server by webhook,
    including failures, so a handled failure returns 200: a retry would only
    repeat the LLM spend on a PDF that already failed. Crashes (OOM, timeout)
    surface as a non-2xx and Cloud Tasks retries per the queue's policy.

    Auth: Cloud Run IAM (OIDC token from the queue's service account, in
    Authorization) plus the shared JOBS_INTERNAL_SECRET when set, carried in
    X-Jobs-Secret because Cloud Tasks overwrites Authorization. A bearer form
    is accepted for calls that do not go through Cloud Run.
    """
    secret = os.getenv("JOBS_INTERNAL_SECRET", "")
    presented = x_jobs_secret or (authorization or "").removeprefix("Bearer ")
    if secret and presented != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if request.task not in RUNNABLE_TASKS:
        raise HTTPException(status_code=404, detail=f"Unknown task: {request.task}")
    task = celery_app.tasks.get(request.task)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not registered: {request.task}")

    logger.info(f"Running {request.task} as {request.task_id} (pushed)")
    result = task.apply(kwargs=request.kwargs, task_id=request.task_id, throw=False)
    if result.failed():
        logger.error(f"Task {request.task_id} failed: {result.result!r}")
        return {"task_id": request.task_id, "status": "failed", "error": str(result.result)}
    return {"task_id": request.task_id, "status": "completed"}

@app.get("/task/{task_id}/status", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """
    Get the status of a processing task by ID.
    """
    try:
        # Get task result from Celery
        task_result = celery_app.AsyncResult(task_id) # type: ignore

        if task_result.state == "PENDING":
            # Task is waiting or doesn't exist
            status_response = TaskStatus(
                task_id=task_id,
                status="pending",
                meta={"message": "Task is pending or does not exist"}
            )
        elif task_result.state == "PROGRESS":
            # Task is in progress - extract progress details
            progress_info = task_result.info or {}
            status_response = TaskStatus(
                task_id=task_id,
                status="running",
                meta=progress_info,
                progress_message=progress_info.get("status", "Processing...")
            )
        elif task_result.state == "SUCCESS":
            # Task completed successfully
            status_response = TaskStatus(
                task_id=task_id,
                status="completed",
                result=task_result.result,
                meta={"completed_at": str(task_result.date_done)}
            )
        elif task_result.state == "FAILURE":
            # Task failed
            status_response = TaskStatus(
                task_id=task_id,
                status="failed",
                error=str(task_result.info),
                meta={"failed_at": str(task_result.date_done)}
            )
        else:
            # Unknown state
            status_response = TaskStatus(
                task_id=task_id,
                status=task_result.state.lower(),
                meta={"info": str(task_result.info)}
            )

        return status_response

    except Exception as e:
        logger.error(f"Failed to get task status for {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")


@app.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    """
    Cancel a pending or running task.
    """
    try:
        celery_app.control.revoke(task_id, terminate=True) # type: ignore
        logger.info(f"Cancelled task {task_id}")
        return {"message": f"Task {task_id} has been cancelled"}

    except Exception as e:
        logger.error(f"Failed to cancel task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel task: {str(e)}")


@app.get("/worker/status")
async def get_worker_status():
    """
    Get status of Celery workers.
    """
    try:
        # Inspect active tasks and worker status
        inspect = celery_app.control.inspect()

        active_tasks = inspect.active()
        registered_tasks = inspect.registered()
        worker_stats = inspect.stats()

        return {
            "active_tasks": active_tasks,
            "registered_tasks": registered_tasks,
            "worker_stats": worker_stats
        }

    except Exception as e:
        logger.error(f"Failed to get worker status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get worker status: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
