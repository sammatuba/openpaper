import logging
import uuid
from typing import List, Optional

from app.database.crud.message_crud import not_a_tutoring_turn
from app.database.crud.projects.project_base_crud import ProjectBaseCRUD
from app.database.crud.projects.project_crud import project_crud
from app.database.models import (
    ConversableType,
    Conversation,
    Message,
    ProjectRole,
    ProjectRoles,
)
from app.schemas.user import CurrentUser
from pydantic import BaseModel
from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ProjectConversationBase(BaseModel):
    title: Optional[str] = None


class ProjectConversationCreate(ProjectConversationBase):
    pass


class ProjectConversationUpdate(ProjectConversationBase):
    pass


class ProjectConversationCRUD(
    ProjectBaseCRUD[Conversation, ProjectConversationCreate, ProjectConversationUpdate]
):
    def create(
        self,
        db: Session,
        *,
        obj_in: ProjectConversationCreate,
        user: Optional[CurrentUser] = None,
        project_id: Optional[uuid.UUID] = None,
    ) -> Optional[Conversation]:
        # Validate required parameters for this implementation
        if user is None:
            raise ValueError(
                "user parameter is required for ProjectConversationCRUD.create"
            )
        if project_id is None:
            raise ValueError(
                "project_id parameter is required for ProjectConversationCRUD.create"
            )

        try:
            # Check if the user has permission to create in this project
            project_role = (
                db.query(ProjectRole)
                .filter(
                    ProjectRole.project_id == project_id,
                    ProjectRole.user_id == user.id,
                    ProjectRole.role.in_([ProjectRoles.ADMIN, ProjectRoles.EDITOR]),
                )
                .first()
            )
            if not project_role:
                return None

            db_obj = Conversation(
                title=obj_in.title,
                user_id=user.id,
                conversable_id=project_id,
                conversable_type=ConversableType.PROJECT,
            )
            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)

            # Touch project updated_at so it sorts to top of recent projects
            project_crud.touch(db, project_id)

            return db_obj
        except Exception as e:
            db.rollback()
            logger.error(
                f"Error creating {self.model.__name__}: {str(e)}", exc_info=True
            )
            return None

    def get_by_project_id(
        self, db: Session, *, project_id: uuid.UUID, user: CurrentUser
    ) -> List[Conversation]:
        # First, check if the user has access to the project.
        project_role = (
            db.query(ProjectRole)
            .filter(
                ProjectRole.project_id == project_id,
                ProjectRole.user_id == user.id,
            )
            .first()
        )
        if not project_role:
            return []

        # A member's tutoring turns are not sent to the project's other
        # members (see message_crud.get_project_conversation_messages), so
        # another member's conversation is listed only once it holds a turn
        # this member can read. One that holds nothing but tutoring turns
        # would open empty and say only that its owner is being tutored. So
        # would one that is still empty: a study session is created, and
        # named, before its first turn is saved, and stays empty for good if
        # that turn never is.
        has_ordinary_turn = exists().where(
            Message.conversation_id == self.model.id,
            *not_a_tutoring_turn(),
        )

        return (
            db.query(self.model)
            .filter(
                self.model.conversable_id == project_id,
                self.model.conversable_type == ConversableType.PROJECT,
                or_(self.model.user_id == user.id, has_ordinary_turn),
            )
            .order_by(self.model.updated_at.desc())
            .all()
        )

    def get_by_conversation_id(
        self,
        db: Session,
        *,
        project_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user: CurrentUser,
    ) -> Optional[Conversation]:
        # First, check if the user has access to the project.
        project_role = (
            db.query(ProjectRole)
            .filter(
                ProjectRole.project_id == project_id,
                ProjectRole.user_id == user.id,
            )
            .first()
        )
        if not project_role:
            return None

        # The role checked above is for `project_id`, so the conversation has
        # to be one of that project's. Fetched by id alone, a member of one
        # project could reach a conversation of another by naming their own
        # project with its id.
        return (
            db.query(self.model)
            .filter(
                self.model.id == conversation_id,
                self.model.conversable_id == project_id,
                self.model.conversable_type == ConversableType.PROJECT,
            )
            .first()
        )


project_conversation_crud = ProjectConversationCRUD(Conversation)
