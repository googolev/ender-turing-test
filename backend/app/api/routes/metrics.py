from fastapi import APIRouter, Depends
from sqlmodel import col, func, select

from app.api.deps import SessionDep, require_permission
from app.core.permissions import Permission, UserRole
from app.models import Item, MetricsPublic, User

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/",
    dependencies=[Depends(require_permission(Permission.METRICS_READ))],
    response_model=MetricsPublic,
)
def read_metrics(session: SessionDep) -> MetricsPublic:
    """
    Basic usage numbers. A stub for a real metrics page.
    """
    by_role = dict(
        session.exec(select(User.role, func.count()).group_by(col(User.role))).all()
    )
    return MetricsPublic(
        users_total=sum(by_role.values()),
        users_active=session.exec(
            select(func.count()).select_from(User).where(col(User.is_active))
        ).one(),
        users_by_role={role: by_role.get(role, 0) for role in UserRole},
        items_total=session.exec(select(func.count()).select_from(Item)).one(),
    )
