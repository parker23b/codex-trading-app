from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.db.session import get_session
from app.core.ig_broker import IGBrokerError
from app.services.market_overview_service import MarketOverviewService

router = APIRouter()


@router.get("/markets/overview")
def get_market_overview(
    category: str = Query(default="forex"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    service = MarketOverviewService(session)
    try:
        return service.get_category_overview(category)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IGBrokerError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to load market overview from IG: {exc}",
        ) from exc
