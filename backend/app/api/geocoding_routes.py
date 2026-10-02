from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user
from app.geocoding.nominatim_client import (
    NominatimBusyError,
    NominatimTimeoutError,
    NominatimUpstreamError,
    search_places,
)
from app.geocoding.schemas import GeocodingResult, GeocodingSearchResponse


router = APIRouter(
    prefix="/api/geocoding",
    tags=["geocoding"],
)


@router.get(
    "/search",
    response_model=GeocodingSearchResponse,
)
def geocode_search(
    q: str = Query(
        ...,
        min_length=2,
        max_length=200,
        description="Place name or address to search",
    ),
    current_user=Depends(get_current_user),
) -> GeocodingSearchResponse:
    del current_user

    query = " ".join(q.strip().split())

    if len(query) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter at least 2 characters to search.",
        )

    try:
        places = search_places(query)

    except NominatimBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc

    except NominatimTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc

    except NominatimUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    results = [
        GeocodingResult(
            display_name=place.display_name,
            latitude=place.latitude,
            longitude=place.longitude,
            type=place.type,
            category=place.category,
        )
        for place in places
    ]

    return GeocodingSearchResponse(
        query=query,
        results=results,
    )