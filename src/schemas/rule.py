# src/schemas/rule.py
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
    UUID4,
    ValidationInfo,
)
from typing import Optional, List, Any
from datetime import datetime

# Import ENUMs defined earlier
from .enums import RuleTypeEnum, TargetTypeEnum

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
            self.max_clicks = None
        elif self.rule_type == RuleTypeEnum.CLICKS:
            if self.max_clicks is None:
                raise ValueError('max_clicks is required for rule_type "clicks"')
            if self.max_clicks <= 0:
                raise ValueError(
                    'max_clicks must be a positive integer for rule_type "clicks"'
                )
            self.start_time = None
            self.end_time = None
        return self

    @field_validator("target_value")
    # pylint: disable=no-self-argument <<< Ignoruj błąd Pylint E0213
    def validate_target_value_format(cls, v: str, info: ValidationInfo) -> str:
        """Validate target_value format based on target_type."""
        target_type_field = info.data.get("target_type")
        if target_type_field == TargetTypeEnum.URL:
            if not v.startswith(("http://", "https://")):
                raise ValueError(
                    'Invalid URL format for target_value when target_type is "url"'
                )
        # TODO: Add HTML length validation if needed
        return v


class RuleUpdate(BaseModel):
    """
    Schema for data allowed when updating a rule.
    Used as request body for PATCH /links/{link_id}/rules/{rule_id}.
    All fields are optional for PATCH operation.
    """

    priority: Optional[int] = Field(
        default=None,  # Użyj default=None w Field, jeśli chcesz zachować inne opcje Field
        gt=0,
        description="New execution priority (positive integer, unique per link).",
    )
    # Dla pól bez dodatkowych opcji Field, wystarczy '= None'
    rule_type: Optional[RuleTypeEnum] = None
    target_type: Optional[TargetTypeEnum] = None
    target_value: Optional[str] = None
    start_time: Optional[datetime | None] = None
    end_time: Optional[datetime | None] = None
    max_clicks: Optional[int | None] = Field(
        default=None,  # Użyj default=None w Field
        gt=0,
        description="New max clicks (positive integer) if rule_type is 'clicks'. Can be set to null.",
    )

    # Walidatory pól (działają tylko gdy pole jest podane w danych wejściowych)
    @field_validator("priority")
    @classmethod
    def validate_priority_positive(cls, v: Optional[int]):
        """Validate priority is positive if provided."""
        # Walidacja gt=0 jest już w Field, ale zostawiamy dla przykładu
        if v is not None and v <= 0:
            raise ValueError("priority must be positive if provided")
        return v

    @field_validator("max_clicks")
    @classmethod
    def validate_max_clicks_positive(cls, v: Optional[int | None]):
        """Validate max_clicks is positive if provided."""
        # Walidacja gt=0 jest już w Field, ale zostawiamy dla przykładu
        if v is not None and v <= 0:
            raise ValueError("max_clicks must be positive if provided")
        return v

    @field_validator("target_value")
    # pylint: disable=no-self-argument
    def validate_target_value_update(
        cls, v: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        """
        Limited validation for target_value during update.
        Checks URL format only if target_type is also being updated to 'url'.
        """
        target_type_in_update = info.data.get("target_type")
        if (
            target_type_in_update == TargetTypeEnum.URL
            and v is not None
            and not v.startswith(("http://", "https://"))
        ):
            raise ValueError(
                'Invalid URL format for target_value when target_type is updated to "url"'
            )
        # TODO: Add HTML length validation
        return v


# --- Data Transfer Objects (Output) ---
class RuleResponse(BaseModel):
    """
    Schema for representing a rule when returned by the API.
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

    model_config = ConfigDict(from_attributes=True)
