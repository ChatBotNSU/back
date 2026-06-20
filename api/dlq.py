from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.auth import require_api_key
from api.deps import DeadLetterStoreDep

router = APIRouter(
    prefix="/api/dead-letter",
    tags=["dead-letter"],
    dependencies=[Depends(require_api_key)],
)


@router.get("")
async def list_dead_letter(dlq: DeadLetterStoreDep, limit: int = 100) -> dict[str, Any]:
    entries = await dlq.list(limit=limit)
    return {
        "count": await dlq.count(),
        "entries": [e.to_dict() for e in entries],
    }


@router.delete("", status_code=204)
async def clear_dead_letter(dlq: DeadLetterStoreDep) -> None:
    await dlq.clear()
