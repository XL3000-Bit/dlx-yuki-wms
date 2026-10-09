from typing import Any
from pydantic import BaseModel
class OutboundWorkbenchResponse(BaseModel): data:list[dict[str,Any]];meta:dict[str,Any];summary:dict[str,Any];status_counts:dict[str,int]
class OutboundWorkbenchDetail(BaseModel): basic:dict[str,Any];allocations:list[dict[str,Any]];picking:list[dict[str,Any]];bols:list[dict[str,Any]];remaining_sources:list[dict[str,Any]];summary:dict[str,Any];workflow:list[dict[str,Any]];audit:list[dict[str,Any]];allowed_actions:dict[str,bool]
