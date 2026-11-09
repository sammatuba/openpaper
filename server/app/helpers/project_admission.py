"""Serialize project-quota admissions across MCP, browser and invitations."""
from app.database.models import User


def lock_project_admissions(db, user):
    """Hold this user's row lock until the caller commits or rolls back.

    All paths adding an accessible project use this lock before checking quota.
    PostgreSQL's default READ COMMITTED isolation lets the subsequent count see
    the preceding admission after waiting for its transaction to finish.
    """
    db.query(User.id).filter(User.id == user.id).with_for_update().one()


def require_project_capacity(db, user):
    # Lazy import avoids subscription_limits -> project_crud import cycles.
    from app.helpers.subscription_limits import can_user_create_project

    permitted, reason = can_user_create_project(db, user)
    if not permitted:
        raise PermissionError(reason or "Project creation limit reached")
