# src/schemas/enums.py
from enum import Enum


class RuleTypeEnum(str, Enum):
    """Database ENUM type for routing_rules.rule_type"""

    TIME = "time"
    CLICKS = "clicks"


class TargetTypeEnum(str, Enum):
    """Database ENUM type for routing_rules.target_type"""

    URL = "url"
    HTML = "html"


# Note: Using standard Python Enums. FastAPI can automatically handle them
# in request/response models if defined correctly.
