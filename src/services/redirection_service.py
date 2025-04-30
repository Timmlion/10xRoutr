# src/services/redirection_service.py

import traceback  # For printing detailed exception stack traces
from enum import Enum
from typing import Optional, Tuple, Any, Dict, List
from uuid import UUID
from datetime import datetime, timezone

# Supabase imports
from supabase import AsyncClient
from postgrest.exceptions import APIError as PostgrestAPIError

# Custom application exceptions
from src.services.custom_exceptions import LinkNotFoundException, DatabaseException

# Schema imports (for Enum comparisons)
from src.schemas.enums import RuleTypeEnum, TargetTypeEnum


class RedirectionAction(Enum):
    """
    Defines the possible outcomes determined by the redirection service
    after evaluating the alias and rules.
    """

    REDIRECT_URL = "redirect_url"  # Redirect to a URL specified by a rule.
    SERVE_HTML = "serve_html"  # Serve HTML content specified by a rule.
    REDIRECT_DEFAULT = "redirect_default"  # Redirect to the link's default URL.
    REDIRECT_GLOBAL_FALLBACK = (
        "redirect_global_fallback"  # Redirect to the application's global fallback URL.
    )


class RedirectionService:
    """
    Handles the core logic for public link redirection.

    It receives an alias path, finds the corresponding link, evaluates its associated
    routing rules based on priority and conditions (time, clicks), increments relevant
    click counters, and ultimately determines the final action (redirect to a URL,
    serve HTML, redirect to the link's default URL, or redirect to a global fallback).

    IMPORTANT: This service requires a Supabase client initialized with the
    `service_role` key to bypass Row Level Security (RLS) for reading any link/rule data
    and executing RPC functions to increment counters.
    """

    def __init__(self, supabase_client: AsyncClient):
        """
        Initializes the RedirectionService.

        Args:
            supabase_client: An instance of Supabase AsyncClient configured with
                             service_role privileges.
        """
        self.supabase_client = supabase_client

    async def _parse_iso_datetime(
        self, datetime_str: Optional[str]
    ) -> Optional[datetime]:
        """
        Safely parses an ISO 8601 formatted datetime string (potentially with timezone)
        into a timezone-aware datetime object (defaulting to UTC if no timezone is specified).

        Args:
            datetime_str: The ISO 8601 datetime string to parse.

        Returns:
            A timezone-aware datetime object, or None if parsing fails or input is None.
        """
        if not datetime_str:
            return None
        try:
            # Parse the ISO string
            dt = datetime.fromisoformat(datetime_str)
            # Ensure the datetime object is timezone-aware (assume UTC if naive)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            # Log error if parsing fails
            print(f"ERROR: Could not parse datetime string: {datetime_str}")  # MVP Log
            return None

    async def process_redirection(
        self, alias_path: str
    ) -> Tuple[RedirectionAction, Optional[str]]:
        """
        Processes a redirection request for a given alias path.

        This involves:
        1. Finding the link matching the alias.
        2. Incrementing the link's total click count.
        3. Fetching associated routing rules, ordered by priority.
        4. Evaluating rules one by one until a match is found based on type (time/clicks).
        5. If a rule matches, incrementing its click count and determining the action (URL/HTML).
        6. If no rule matches, checking for a link-specific default URL.
        7. If no rule matches and no default URL exists, determining a global fallback action.

        Args:
            alias_path: The path segment from the URL, treated as the link alias.

        Returns:
            A tuple containing the determined RedirectionAction (Enum) and an
            optional string value (URL or HTML content) associated with the action.

        Raises:
            LinkNotFoundException: If no link matches the provided alias_path.
            DatabaseException: For errors during database interactions (fetching link/rules, RPC calls).
        """
        link_id: Optional[UUID] = None
        default_url: Optional[str] = None

        # --- Step 1: Find the Link by Alias ---
        try:
            print(f"Searching for link with alias: {alias_path}")  # MVP Log
            # Query the database for the link using the service client (bypasses RLS)
            response = (
                await self.supabase_client.table("routr_links")
                .select("id, default_url")  # Select only necessary fields
                .eq("alias", alias_path)
                .limit(1)
                .maybe_single()  # Returns None if not found, doesn't raise error
                .execute()
            )
            print(
                f"Supabase response for alias '{alias_path}': {response}"
            )  # MVP Log (for debugging)

            # Check if the query returned data
            if not (response and response.data):
                print(f"Link alias not found: {alias_path}")  # MVP Log
                # Raise specific exception if link doesn't exist
                raise LinkNotFoundException(
                    detail=f"Link alias '{alias_path}' not found."
                )

            # Extract link ID and default URL if found
            link_data = response.data
            link_id = UUID(link_data["id"])
            default_url = link_data.get(
                "default_url"
            )  # Safely get default_url, might be None
            print(f"Found link ID: {link_id}, Default URL: {default_url}")  # MVP Log

        except PostgrestAPIError as e:
            # Handle specific database API errors during link fetch
            print(
                f"Database API error occurred while fetching link '{alias_path}': {e}"
            )  # MVP Log
            raise DatabaseException(
                detail=f"Database error fetching link: {getattr(e,'message','Unknown error')}"
            ) from e
        except LinkNotFoundException:
            # Re-raise LinkNotFoundException to be handled by the caller (e.g., main API endpoint)
            raise
        except Exception as e:
            # Handle any other unexpected errors during link fetch
            print(f"Unexpected error fetching link '{alias_path}':")  # MVP Log
            traceback.print_exc()
            raise DatabaseException(
                detail=f"Unexpected error fetching link: {e}"
            ) from e

        # --- Step 2: Increment Link's Total Click Count (Best Effort) ---
        # This is done early, regardless of rule matching, to track all attempts to access the alias.
        if link_id:
            try:
                print(
                    f"Attempting to increment total clicks for link ID: {link_id}"
                )  # MVP Log
                # Call the database function 'increment_link_clicks' using RPC
                await self.supabase_client.rpc(
                    "increment_link_clicks", {"link_uuid": str(link_id)}
                ).execute()
                print(
                    f"Successfully called RPC increment_link_clicks for link ID: {link_id}"
                )  # MVP Log
            except (PostgrestAPIError, Exception) as e:
                # Log errors during RPC call but continue processing the redirection.
                # Failing to increment the counter shouldn't block the user's redirection.
                error_msg = getattr(e, "message", str(e))
                print(
                    f"ERROR: Failed incrementing total clicks for link {link_id}: {error_msg}. Continuing redirection."
                )  # MVP Log
                if not isinstance(e, PostgrestAPIError):
                    traceback.print_exc()  # Print stack trace for non-Postgrest errors

        # --- Step 3: Fetch Routing Rules for the Link ---
        rules: List[Dict[str, Any]] = []
        try:
            print(f"Fetching rules for link ID: {link_id}")  # MVP Log
            # Query the rules table, ordered by priority (ascending, lower number = higher priority)
            rules_response = (
                await self.supabase_client.table("routing_rules")
                .select(
                    "id, priority, rule_type, target_type, target_value, start_time, end_time, max_clicks, current_clicks"
                )
                .eq("link_id", str(link_id))  # Filter rules for the found link
                .order(
                    "priority", desc=False
                )  # Ensure evaluation respects priority order
                .execute()
            )
            # Extract the list of rules, default to empty list if none found
            rules = (
                rules_response.data if rules_response and rules_response.data else []
            )
            print(f"Fetched {len(rules)} rules for link ID: {link_id}")  # MVP Log

        except PostgrestAPIError as e:
            # Handle specific database API errors during rule fetch
            print(
                f"ERROR: Database API error fetching rules for link {link_id}: {getattr(e,'message','Unknown error')}"
            )  # MVP Log
            raise DatabaseException(
                detail=f"Database error fetching rules: {getattr(e,'message','Unknown error')}"
            ) from e
        except Exception as e:
            # Handle any other unexpected errors during rule fetch
            print(
                f"ERROR: Unexpected error fetching rules for link {link_id}:"
            )  # MVP Log
            traceback.print_exc()
            raise DatabaseException(
                detail=f"Unexpected error fetching rules: {e}"
            ) from e

        # --- Step 4: Evaluate Rules in Priority Order ---
        rule_matched = False
        matched_rule: Optional[Dict[str, Any]] = None
        now_utc = datetime.now(timezone.utc)  # Get current time in UTC for comparisons

        print(f"Evaluating rules at time: {now_utc.isoformat()}")  # MVP Log

        for rule in rules:
            rule_id_str = rule.get("id", "N/A")
            print(
                f"Evaluating rule ID: {rule_id_str}, Priority: {rule.get('priority','N/A')}, Type: {rule.get('rule_type','N/A')}"
            )  # MVP Log
            current_rule_matched = False
            try:
                rule_type = rule.get("rule_type")

                # Evaluate based on rule type
                if rule_type == RuleTypeEnum.TIME.value:
                    # Parse start and end times safely
                    start_time = await self._parse_iso_datetime(rule.get("start_time"))
                    end_time = await self._parse_iso_datetime(rule.get("end_time"))
                    # Check if current time falls within the valid range
                    if start_time and end_time and (start_time <= now_utc <= end_time):
                        print(f"Rule {rule_id_str} (time) MATCHED")  # MVP Log
                        current_rule_matched = True
                    else:
                        # Log why it didn't match (if times were valid)
                        if start_time and end_time:
                            print(
                                f"Rule {rule_id_str} (time) NOT MATCHED: Current time outside range."
                            )  # MVP Log
                        else:
                            print(
                                f"Rule {rule_id_str} (time) SKIPPED: Invalid or missing times."
                            )  # MVP Log

                elif rule_type == RuleTypeEnum.CLICKS.value:
                    current_clicks = rule.get("current_clicks")
                    max_clicks = rule.get("max_clicks")
                    # Check if click counts are valid integers and limit not reached
                    if isinstance(current_clicks, int) and isinstance(max_clicks, int):
                        if current_clicks < max_clicks:
                            print(
                                f"Rule {rule_id_str} (clicks) MATCHED: {current_clicks} < {max_clicks}"
                            )  # MVP Log
                            current_rule_matched = True
                        else:
                            print(
                                f"Rule {rule_id_str} (clicks) NOT MATCHED: Limit reached ({current_clicks} >= {max_clicks})"
                            )  # MVP Log
                    else:
                        print(
                            f"Rule {rule_id_str} (clicks) SKIPPED: Invalid or missing click values."
                        )  # MVP Log
                else:
                    # Handle unknown rule types if they somehow exist
                    print(
                        f"Rule {rule_id_str} SKIPPED: Unknown rule type '{rule_type}'."
                    )  # MVP Log

            except Exception as e:
                # Log errors during evaluation of a specific rule but continue to the next
                print(
                    f"ERROR evaluating rule ID {rule_id_str}: {e}. Skipping rule."
                )  # MVP Log
                traceback.print_exc()
                continue  # Move to the next rule

            # If a rule matched, stop evaluating further rules (respecting priority)
            if current_rule_matched:
                rule_matched = True
                matched_rule = rule
                print(
                    f"Rule {matched_rule.get('id','N/A')} selected as the final match."
                )  # MVP Log
                break  # Exit the loop as we found the highest priority match

        # --- Step 5: Determine Final Action Based on Evaluation Result ---
        if rule_matched and matched_rule:
            # --- Increment Matched Rule's Click Count (Best Effort) ---
            matched_rule_id = matched_rule.get("id")
            if matched_rule_id:
                try:
                    print(
                        f"Attempting to increment current clicks for matched rule ID: {matched_rule_id}"
                    )  # MVP Log
                    # Call the database function 'increment_rule_clicks'
                    await self.supabase_client.rpc(
                        "increment_rule_clicks", {"rule_uuid": str(matched_rule_id)}
                    ).execute()
                    print(
                        f"Successfully called RPC increment_rule_clicks for rule ID: {matched_rule_id}"
                    )  # MVP Log
                except (PostgrestAPIError, Exception) as e:
                    # Log errors but continue - don't block redirection
                    error_msg = getattr(e, "message", str(e))
                    print(
                        f"ERROR: Failed incrementing clicks for rule {matched_rule_id}: {error_msg}. Continuing redirection."
                    )  # MVP Log
                    if not isinstance(e, PostgrestAPIError):
                        traceback.print_exc()
            else:
                # Should not happen if data fetching is correct
                print(
                    "ERROR: Matched rule data is missing 'id'. Cannot increment rule counter."
                )  # MVP Log

            # --- Determine Action based on Matched Rule's Target Type ---
            target_type = matched_rule.get("target_type")
            target_value = matched_rule.get("target_value")  # URL or HTML content

            if target_type == TargetTypeEnum.URL.value:
                print(f"Action: REDIRECT_URL to {target_value}")  # MVP Log
                return (RedirectionAction.REDIRECT_URL, target_value)
            elif target_type == TargetTypeEnum.HTML.value:
                print("Action: SERVE_HTML")  # MVP Log
                return (RedirectionAction.SERVE_HTML, target_value)
            else:
                # Fallback if target_type is somehow invalid for the matched rule
                print(
                    f"ERROR: Matched rule {matched_rule_id} has unknown target_type: {target_type}. Falling back."
                )  # MVP Log
                # Treat as if no rule matched, leading to default or global fallback
                # Returning GLOBAL_FALLBACK directly here for safety.
                return (RedirectionAction.REDIRECT_GLOBAL_FALLBACK, None)
        else:
            # --- No Rule Matched: Use Default URL or Global Fallback ---
            print("No rule matched.")  # MVP Log
            if default_url:
                # If a link-specific default URL exists, use it
                print(f"Action: REDIRECT_DEFAULT to {default_url}")  # MVP Log
                return (RedirectionAction.REDIRECT_DEFAULT, default_url)
            else:
                # If no rule matched and no default URL, use the global fallback
                print(
                    "Action: REDIRECT_GLOBAL_FALLBACK (no default URL defined)"
                )  # MVP Log
                return (RedirectionAction.REDIRECT_GLOBAL_FALLBACK, None)
