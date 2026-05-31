from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.crud.base import CRUDBase
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


class CRUDProject(CRUDBase[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, model: type[Project] = Project):
        super().__init__(model)

    async def add_collaborators(
        self, db: AsyncSession, *, project_id: UUID, colaborators: List[UUID]
    ) -> Optional[Project]:
        project = await self.get(db, id=project_id)
        if not project:
            return None
        
        # Merge existing collaborators with new ones, avoiding duplicates
        existing_colaborators = project.colaborators or []
        merged_colaborators = list(set(existing_colaborators + colaborators))
        project.colaborators = merged_colaborators
        
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project

    async def get_user_projects(
        self, db: AsyncSession, *, user_id: UUID
    ) -> dict[str, List[UUID]]:
        # Get projects where user is owner
        owner_result = await db.execute(
            select(Project.id).where(Project.user_id == user_id)
        )
        owned_projects = [row[0] for row in owner_result.fetchall()]
        
        # Get projects where user is collaborator
        collaborator_result = await db.execute(
            select(Project.id).where(Project.colaborators.contains([user_id]))
        )
        collaborator_projects = [row[0] for row in collaborator_result.fetchall()]
        
        return {
            "owned_projects": owned_projects,
            "collaborator_projects": collaborator_projects
        }


project = CRUDProject()
