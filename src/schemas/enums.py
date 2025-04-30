# src/schemas/enums.py
from enum import Enum

# This module defines Enumerations used throughout the application,
# particularly mirroring ENUM types defined in the database schema.
# Using Enums improves code readability and prevents typos compared to using raw strings.


class RuleTypeEnum(str, Enum):
    """
    Represents the possible types of conditions a routing rule can have.
    Maps directly to the 'rule_type' ENUM in the 'routing_rules' database table.

    Attributes:
        TIME: Rule is based on a time window (start_time, end_time).
        CLICKS: Rule is based on a maximum click count (max_clicks).
    """

    TIME = "time"
    CLICKS = "clicks"


class TargetTypeEnum(str, Enum):
    """
    Represents the possible types of actions or destinations for a routing rule.
    Maps directly to the 'target_type' ENUM in the 'routing_rules' database table.

    Attributes:
        URL: The rule redirects the user to a specific URL (stored in target_value).
        HTML: The rule serves raw HTML content directly to the user (stored in target_value).
    """

    URL = "url"
    HTML = "html"


# Note: By inheriting from `str` and `Enum`, these enums can be easily
# serialized/deserialized by FastAPI and Pydantic, allowing them to be used
# directly in request/response models and validated against the defined members.
