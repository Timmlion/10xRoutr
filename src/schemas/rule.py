# src/schemas/rule.py
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
    UUID4,
    HttpUrl,
)
from typing import Optional, List, Any
from datetime import datetime

# Import ENUMs defined earlier
from .enums import RuleTypeEnum, TargetTypeEnum

# --- Base Model ---
# Less useful here due to complex conditional fields in Create/Update

# --- Command Models (Input) ---


class RuleCreate(BaseModel):
    """
    Schema for data required to create a new routing rule.
    Used as request body for POST /links/{link_id}/rules.
    """

    priority: int = Field(
        ...,
        gt=0,
        description="Execution priority (positive integer, lower number = higher priority), unique per link.",
    )
    rule_type: RuleTypeEnum = Field(
        ..., description="Type of condition for this rule ('time' or 'clicks')."
    )
    target_type: TargetTypeEnum = Field(
        ..., description="Type of destination ('url' or 'html')."
    )
    target_value: str = Field(
        ..., description="The destination URL or the raw HTML content."
    )
    start_time: Optional[datetime] = Field(
        None, description="Start time (UTC) for time-based rules."
    )
    end_time: Optional[datetime] = Field(
        None, description="End time (UTC) for time-based rules."
    )
    max_clicks: Optional[int] = Field(
        None,
        gt=0,
        description="Maximum clicks (positive integer) for clicks-based rules.",
    )

    # Pydantic v2+ style model validator
    @model_validator(mode="after")
    def check_conditional_fields(self) -> "RuleCreate":
        """Ensure required fields are present based on rule_type and clear irrelevant fields."""
        if self.rule_type == RuleTypeEnum.TIME:
            if self.start_time is None or self.end_time is None:
                raise ValueError(
                    'start_time and end_time are required for rule_type "time"'
                )
            if self.start_time >= self.end_time:
                raise ValueError(
                    'end_time must be after start_time for rule_type "time"'
                )
            # Clear clicks field if type is time
            self.max_clicks = None
        elif self.rule_type == RuleTypeEnum.CLICKS:
            if self.max_clicks is None:
                raise ValueError('max_clicks is required for rule_type "clicks"')
            # Clear time fields if type is clicks
            self.start_time = None
            self.end_time = None
        return self

    @field_validator("target_value")
    def validate_target_value_format(cls, v: str, info: FieldValidationInfo) -> str:
        """Validate target_value format based on target_type."""
        # info.data holds the partially validated model data in Pydantic v2
        if (
            "target_type" in info.data
            and info.data["target_type"] == TargetTypeEnum.URL
        ):
            # Basic check, consider using HttpUrl type for target_value if possible
            # or a more robust validation library
            if not (v.startswith("http://") or v.startswith("https://")):
                raise ValueError(
                    'Invalid URL format for target_value when target_type is "url"'
                )
        # Add HTML length check here if limit is defined
        # if 'target_type' in info.data and info.data['target_type'] == TargetTypeEnum.HTML:
        # if len(v) > YOUR_HTML_LIMIT:
        #     raise ValueError(f"HTML content exceeds limit of {YOUR_HTML_LIMIT}")
        return v


class RuleUpdate(BaseModel):
    """
    Schema for data allowed when updating a rule.
    Used as request body for PATCH /links/{link_id}/rules/{rule_id}.
    All fields are optional. Complex validation (dependencies between fields)
    should primarily happen in the service layer after fetching the current rule state.
    """

    priority: Optional[int] = Field(
        None,
        gt=0,
        description="New execution priority (positive integer, unique per link).",
    )
    rule_type: Optional[RuleTypeEnum] = Field(
        None,
        description="Change the rule type ('time' or 'clicks'). Requires related fields to be set consistently.",
    )
    target_type: Optional[TargetTypeEnum] = Field(
        None,
        description="Change the target type ('url' or 'html'). Requires target_value format validation.",
    )
    target_value: Optional[str] = Field(
        None, description="New target value (URL or HTML)."
    )
    start_time: Optional[datetime | None] = Field(
        None,
        description="New start time (UTC) if rule_type is 'time'. Can be set to null.",
    )
    end_time: Optional[datetime | None] = Field(
        None,
        description="New end time (UTC) if rule_type is 'time'. Can be set to null.",
    )
    max_clicks: Optional[int | None] = Field(
        None,
        gt=0,
        description="New max clicks (positive integer) if rule_type is 'clicks'. Can be set to null.",
    )

    # Basic validators can remain, but complex cross-field validation is deferred to service layer for PATCH
    @field_validator("priority")
    def validate_priority_positive(cls, v: Optional[int]):
        if v is not None and v <= 0:
            raise ValueError("priority must be positive")
        return v

    @field_validator("max_clicks")
    def validate_max_clicks_positive(cls, v: Optional[int | None]):
        # Allows explicit None to clear field if rule_type changes
        if v is not None and v <= 0:
            raise ValueError("max_clicks must be positive if provided")
        return v

    # Limited target_value validation - service layer needs full context
    @field_validator("target_value")
    def validate_target_value_update(
        cls, v: Optional[str], info: FieldValidationInfo
    ) -> Optional[str]:
        # This can only validate if target_type is *also* being updated in the same request
        target_type = (
            info.data.get("target_type") if "target_type" in info.data else None
        )  # Or fetch current type in service
        if (
            target_type == TargetTypeEnum.URL
            and v is not None
            and not (v.startswith("http://") or v.startswith("https://"))
        ):
            raise ValueError(
                'Invalid URL format for target_value when target_type is "url"'
            )
        # Add HTML length check here
        return v


# --- Data Transfer Objects (Output) ---


class RuleResponse(BaseModel):
    """
    Schema for representing a rule when returned by the API.
    Used as response body for GET /links/{link_id}/rules/{rule_id},
    POST /links/{link_id}/rules, PATCH /links/{link_id}/rules/{rule_id},
    and as items in GET /links/{link_id}/rules list.
    """

    id: UUID4
    link_id: UUID4
    priority: int
    rule_type: RuleTypeEnum
    target_type: TargetTypeEnum
    target_value: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    max_clicks: Optional[int] = None
    current_clicks: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)  # Enable ORM mode (Pydantic v2+)
    # Pydantic v1 equivalent:
    # class Config:
    #     orm_mode = True
