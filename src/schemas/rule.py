# src/schemas/rule.py
from pydantic import (
    BaseModel,
    Field,
    field_validator,  # Decorator for validating individual fields
    model_validator,  # Decorator for validating the entire model after individual fields
    ConfigDict,
    UUID4,  # Represents a UUID type
    HttpUrl,  # Used implicitly by URL validation logic
    ValidationInfo,  # Provides context to validators (e.g., other field values)
)
from typing import Optional, List, Any
from datetime import datetime

# Import custom Enums for rule types and target types
from .enums import RuleTypeEnum, TargetTypeEnum

# --- Command Models (Input Schemas) ---
# These models define the expected structure for incoming request data to create or update rules.


class RuleCreate(BaseModel):
    """
    Schema validating the data required to create a new routing rule.
    Used as the request body structure for POST /api/v1/links/{link_id}/rules.
    """

    priority: int = Field(
        ...,  # Indicates the field is required
        gt=0,  # Ensures the priority is a positive integer (greater than 0).
        description="Execution priority (positive integer, lower number = higher priority), must be unique per link.",
    )
    rule_type: RuleTypeEnum = Field(
        ...,  # Required field
        description="Type of condition for this rule ('time' or 'clicks'). Uses RuleTypeEnum.",
    )
    target_type: TargetTypeEnum = Field(
        ...,  # Required field
        description="Type of destination ('url' or 'html'). Uses TargetTypeEnum.",
    )
    target_value: str = Field(
        ...,  # Required field
        description="The destination URL (if target_type='url') or the raw HTML content (if target_type='html').",
    )
    # Optional fields, their necessity is checked by the model_validator based on rule_type.
    start_time: Optional[datetime] = Field(
        None,
        description="Start time (UTC) for time-based rules (required if rule_type='time').",
    )
    end_time: Optional[datetime] = Field(
        None,
        description="End time (UTC) for time-based rules (required if rule_type='time').",
    )
    max_clicks: Optional[int] = Field(
        None,
        gt=0,  # Ensures max_clicks is positive if provided.
        description="Maximum clicks (positive integer) for clicks-based rules (required if rule_type='clicks').",
    )

    @model_validator(mode="after")  # Runs after individual field validation
    def check_conditional_fields(self) -> "RuleCreate":
        """
        Validates conditional requirements based on 'rule_type'.
        - If rule_type is TIME, ensures start_time and end_time are present and valid. Clears max_clicks.
        - If rule_type is CLICKS, ensures max_clicks is present and valid. Clears start_time and end_time.
        """
        if self.rule_type == RuleTypeEnum.TIME:
            # Check required fields for TIME rules
            if self.start_time is None or self.end_time is None:
                raise ValueError(
                    'start_time and end_time are required for rule_type "time"'
                )
            # Check logical constraint for TIME rules
            if self.start_time >= self.end_time:
                raise ValueError(
                    'end_time must be after start_time for rule_type "time"'
                )
            # Ensure irrelevant field is cleared
            self.max_clicks = None
        elif self.rule_type == RuleTypeEnum.CLICKS:
            # Check required field for CLICKS rules
            if self.max_clicks is None:
                raise ValueError('max_clicks is required for rule_type "clicks"')
            # Check logical constraint (already covered by gt=0 in Field, but provides clearer error)
            if self.max_clicks <= 0:
                raise ValueError(
                    'max_clicks must be a positive integer for rule_type "clicks"'
                )
            # Ensure irrelevant fields are cleared
            self.start_time = None
            self.end_time = None
        return self  # Must return the model instance

    @field_validator("target_value")
    # @classmethod # Use classmethod if 'self' is not needed
    def validate_target_value_format(cls, v: str, info: ValidationInfo) -> str:
        """
        Validates the format of 'target_value' based on the 'target_type'.
        Uses `ValidationInfo` to access the value of 'target_type' within the same model.
        """
        target_type_field = info.data.get(
            "target_type"
        )  # Get value of target_type if present
        if target_type_field == TargetTypeEnum.URL:
            # Basic check if the value looks like a URL when type is URL.
            # Pydantic's HttpUrl type offers more robust validation if used directly.
            if not v.startswith(("http://", "https://")):
                raise ValueError(
                    'Invalid URL format for target_value when target_type is "url". Must start with http:// or https://'
                )
        elif target_type_field == TargetTypeEnum.HTML:
            # Placeholder for potential future validation on HTML content, e.g., length check.
            pass
        return v


class RuleUpdate(BaseModel):
    """
    Schema validating the data allowed when updating an existing rule via PATCH.
    All fields are optional, allowing for partial updates. Validators ensure that
    if a field *is* provided, it meets basic requirements.
    """

    priority: Optional[int] = Field(
        default=None,  # Use default=None to explicitly mark as optional for PATCH
        gt=0,  # If priority is provided, it must be positive.
        description="New execution priority (positive integer, unique per link).",
    )
    # Optional fields don't need `Field` if no extra constraints/metadata needed besides being Optional.
    rule_type: Optional[RuleTypeEnum] = None
    target_type: Optional[TargetTypeEnum] = None
    target_value: Optional[str] = (
        None  # Allows updating to any string, including empty.
    )
    start_time: Optional[datetime | None] = None  # Allows explicitly setting to null.
    end_time: Optional[datetime | None] = None  # Allows explicitly setting to null.
    max_clicks: Optional[int | None] = Field(
        default=None,
        gt=0,  # If max_clicks is provided (and not null), it must be positive.
        description="New max clicks (positive integer) if rule_type is 'clicks'. Can be set to null.",
    )

    # Field validators in Update schemas typically check constraints *if* the field is provided.
    # Note: Pydantic v2 runs validators even if the field is None unless specified otherwise.
    # The `gt=0` constraint in Field handles the positive check more directly.
    # These validators are kept as examples of how field-specific checks could be done.

    @field_validator("priority")
    @classmethod
    def validate_priority_positive_if_provided(cls, v: Optional[int]):
        """Validate priority is positive *if* a value is provided."""
        if v is not None and v <= 0:
            raise ValueError("priority must be positive if provided")
        return v

    @field_validator("max_clicks")
    @classmethod
    def validate_max_clicks_positive_if_provided(cls, v: Optional[int | None]):
        """Validate max_clicks is positive *if* a non-null value is provided."""
        if v is not None and v <= 0:
            raise ValueError("max_clicks must be positive if provided")
        return v

    @field_validator("target_value")
    def validate_target_value_update_format(
        cls, v: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        """
        Validates 'target_value' format during update, primarily checking for valid URL
        format *if* 'target_type' is also being explicitly set to 'url' in the same request.
        This is less strict than create validation as the target_type might not be changing.
        """
        # Get the target_type *if* it's included in the update payload.
        target_type_in_update = info.data.get("target_type")
        if (
            target_type_in_update
            == TargetTypeEnum.URL  # Only check if type is being set to URL
            and v is not None  # And a target_value is provided
            and not v.startswith(
                ("http://", "https://")
            )  # And it doesn't look like a URL
        ):
            raise ValueError(
                'Invalid URL format for target_value when target_type is updated to "url"'
            )
        # Placeholder for HTML validation if needed
        return v

    # Note: A model_validator could be added to RuleUpdate to check for consistency
    # between fields if multiple fields are updated simultaneously (e.g., if rule_type
    # is changed, ensure the corresponding required fields like max_clicks/start_time are also provided).
    # However, for simple PATCH, often field-level validation is sufficient.


# --- Data Transfer Objects (Output Schemas) ---
# These models define the structure of data returned by the API.


class RuleResponse(BaseModel):
    """
    Schema representing a routing rule as returned by the API.
    Includes all relevant fields stored in the database.
    """

    id: UUID4  # Unique identifier for the rule.
    link_id: UUID4  # Identifier of the parent link this rule belongs to.
    priority: int  # Execution priority.
    rule_type: RuleTypeEnum  # Type of rule condition.
    target_type: TargetTypeEnum  # Type of rule action/destination.
    target_value: str  # The URL or HTML content.
    start_time: Optional[datetime] = None  # Start time if it's a time-based rule.
    end_time: Optional[datetime] = None  # End time if it's a time-based rule.
    max_clicks: Optional[int] = None  # Max clicks if it's a clicks-based rule.
    current_clicks: int  # Counter for clicks-based rules.
    created_at: datetime  # Timestamp when the rule was created.
    updated_at: datetime  # Timestamp when the rule was last updated.

    # Enable ORM mode (from_attributes=True in Pydantic v2) to allow creating
    # this schema directly from database model instances.
    model_config = ConfigDict(from_attributes=True)
