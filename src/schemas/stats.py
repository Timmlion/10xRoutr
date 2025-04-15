# src/schemas/stats.py
from pydantic import BaseModel, UUID4
from typing import List, Optional

# Import ENUMs defined earlier
from enums import TargetTypeEnum


class TargetClickStat(BaseModel):
    """Schema representing click stats for a specific rule's target."""

    rule_id: UUID4 = Field(description="ID of the rule that led to these clicks.")
    target_type: TargetTypeEnum = Field(
        description="The type of the target ('url' or 'html')."
    )
    target_value_preview: str = Field(
        description="The target URL or a placeholder/preview for HTML content."
    )
    current_clicks: int = Field(
        description="Number of clicks recorded for this specific rule."
    )


class LinkStatsResponse(BaseModel):
    """Schema for the response containing statistics for a link."""

    link_id: UUID4 = Field(description="ID of the link these stats belong to.")
    alias: str = Field(description="Alias of the link.")
    total_clicks: int = Field(
        description="Total number of clicks recorded for the link alias."
    )
    target_clicks: List[TargetClickStat] = Field(
        description="List of click counts for each rule's target."
    )
