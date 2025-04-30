# src/schemas/stats.py
from pydantic import BaseModel, UUID4, Field
from typing import List, Optional

# Relative import of Enums from the same directory
from .enums import TargetTypeEnum

# This module defines Pydantic schemas related to statistics,
# primarily for representing click data associated with links and their rules.


class TargetClickStat(BaseModel):
    """
    Represents click statistics specifically attributed to a single routing rule's target.
    This helps break down the total clicks by which rule was matched.
    """

    rule_id: UUID4 = Field(
        description="The unique identifier of the rule responsible for these clicks."
    )
    target_type: TargetTypeEnum = Field(
        description="Indicates whether the rule's target was a URL or HTML content."
    )
    # Provides context about the target without necessarily including the full HTML content.
    target_value_preview: str = Field(
        description="The target URL, or a preview/placeholder if the target was HTML content."
    )
    # This count is specific to this rule, distinct from the link's total clicks.
    current_clicks: int = Field(
        description="Number of clicks recorded specifically for this rule's target."
    )


class LinkStatsResponse(BaseModel):
    """
    Schema defining the structure for the response containing aggregated click statistics for a specific link.
    """

    link_id: UUID4 = Field(
        description="The unique identifier of the link these statistics pertain to."
    )
    alias: str = Field(description="The alias (path segment) of the link.")
    # Represents all clicks hitting the link's alias, regardless of which rule (or default) handled it.
    total_clicks: int = Field(
        description="The overall total number of clicks recorded for this link's alias."
    )
    # Provides a breakdown of clicks per specific rule target.
    target_clicks: List[TargetClickStat] = Field(
        description="A list detailing the click counts for each individual rule's target associated with this link."
    )
