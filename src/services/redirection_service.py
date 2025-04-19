# src/services/redirection_service.py

# Usunięto import logging
import traceback  # Dodano dla print_exc()
from enum import Enum
from typing import Optional, Tuple, Any, Dict, List
from uuid import UUID
from datetime import datetime, timezone

# Import klienta Supabase i potencjalnych błędów
from supabase import AsyncClient  # <<< POPRAWIONY IMPORT
from postgrest.exceptions import APIError as PostgrestAPIError  # <<< POPRAWIONY IMPORT

# Import niestandardowych wyjątków
# Zakładamy, że te wyjątki są zdefiniowane w src/services/custom_exceptions.py
# i mają __init__(self, detail: str = ...)
from src.services.custom_exceptions import LinkNotFoundException, DatabaseException

# Import schematów ENUM (potrzebne do porównań typów)
from src.schemas.enums import RuleTypeEnum, TargetTypeEnum


class RedirectionAction(Enum):
    """Defines the possible outcomes of the redirection evaluation."""

    REDIRECT_URL = "redirect_url"
    SERVE_HTML = "serve_html"
    REDIRECT_DEFAULT = "redirect_default"
    REDIRECT_GLOBAL_FALLBACK = "redirect_global_fallback"


class RedirectionService:
    """
    Service responsible for handling the public redirection logic.
    It finds links by alias, evaluates rules based on priority, increments counters,
    and determines the final redirection action (URL redirect, serve HTML, default, or global fallback).

    IMPORTANT: This service MUST be instantiated with a Supabase client
    configured with the 'service_role' key to bypass RLS policies
    for reading any link/rule data and incrementing counters via RPC functions.
    """

    def __init__(self, supabase_client: AsyncClient):
        """
        Initializes the RedirectionService.

        Args:
            supabase_client: An instance of AsyncClient configured with service_role privileges.
        """
        self.supabase_client = supabase_client

    async def _parse_iso_datetime(
        self, datetime_str: Optional[str]
    ) -> Optional[datetime]:
        """Helper to parse ISO 8601 string with timezone to aware datetime object."""
        if not datetime_str:
            return None
        try:
            dt = datetime.fromisoformat(datetime_str)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            print(f"ERROR: Could not parse datetime string: {datetime_str}")
            return None

    async def process_redirection(
        self, alias_path: str
    ) -> Tuple[RedirectionAction, Optional[str]]:
        """
        Processes a redirection request for a given alias path.
        """
        link_id: Optional[UUID] = None
        default_url: Optional[str] = None

        # --- Krok 4.1: Znajdź Link ---
        try:
            print(f"Searching for link with alias: {alias_path}")
            response = (
                await self.supabase_client.table("routr_links")
                .select("id, default_url")
                .eq("alias", alias_path)
                .limit(1)
                # Użyj maybe_single(), aby obsłużyć brak rekordu bez błędu
                .maybe_single()
                .execute()
            )
            print(
                f"Supabase response for alias '{alias_path}': {response}"
            )  # Loguj całą odpowiedź dla debugowania

            # Sprawdź, czy odpowiedź istnieje i czy zawiera dane
            if not (response and response.data):
                print(f"Link alias not found: {alias_path}")
                # <<< POPRAWKA: Przekaż 'detail' zamiast 'alias'
                raise LinkNotFoundException(
                    detail=f"Link alias '{alias_path}' not found."
                )

            link_data = response.data  # Już wiemy, że response.data istnieje
            link_id = UUID(link_data["id"])
            default_url = link_data.get("default_url")
            print(f"Found link ID: {link_id}, Default URL: {default_url}")

        except PostgrestAPIError as e:
            print(
                f"Database API error occurred while fetching link '{alias_path}': {e}"
            )
            # <<< POPRAWKA: Użyj 'detail' zamiast 'message'
            raise DatabaseException(
                detail=f"Database error fetching link: {getattr(e,'message','Unknown error')}"
            ) from e
        except LinkNotFoundException:  # Przechwyć, aby nie złapał go ogólny Exception
            raise
        except Exception as e:
            print(f"Unexpected error fetching link '{alias_path}':")
            traceback.print_exc()
            # <<< POPRAWKA: Użyj 'detail' zamiast 'message'
            raise DatabaseException(
                detail=f"Unexpected error fetching link: {e}"
            ) from e

        # --- Krok 4.2: Inkrementuj Licznik Linku ---
        if link_id:
            try:
                print(f"Attempting to increment total clicks for link ID: {link_id}")
                await self.supabase_client.rpc(
                    "increment_link_clicks", {"link_uuid": str(link_id)}
                ).execute()
                print(
                    f"Successfully called RPC increment_link_clicks for link ID: {link_id}"
                )
            except PostgrestAPIError as e:
                print(
                    f"ERROR: Database error incrementing total clicks for link {link_id}: {getattr(e,'message','Unknown error')}. Continuing redirection."
                )
            except Exception as e:
                print(
                    f"ERROR: Unexpected error incrementing total clicks for link {link_id}: {e}. Continuing redirection."
                )
                traceback.print_exc()  # Drukuj stack trace dla nieoczekiwanych błędów

        # --- Krok 4.3: Pobierz Reguły ---
        rules: List[Dict[str, Any]] = []
        try:
            print(f"Fetching rules for link ID: {link_id}")
            rules_response = (
                await self.supabase_client.table("routing_rules")
                .select(
                    "id, priority, rule_type, target_type, target_value, start_time, end_time, max_clicks, current_clicks"
                )
                .eq("link_id", str(link_id))
                .order("priority", desc=False)
                .execute()
            )
            # Sprawdź czy odpowiedź istnieje i ma dane
            rules = (
                rules_response.data if rules_response and rules_response.data else []
            )
            print(f"Fetched {len(rules)} rules for link ID: {link_id}")

        except PostgrestAPIError as e:
            print(
                f"ERROR: Database API error fetching rules for link {link_id}: {getattr(e,'message','Unknown error')}"
            )
            # <<< POPRAWKA: Użyj 'detail' zamiast 'message'
            raise DatabaseException(
                detail=f"Database error fetching rules: {getattr(e,'message','Unknown error')}"
            ) from e
        except Exception as e:
            print(f"ERROR: Unexpected error fetching rules for link {link_id}:")
            traceback.print_exc()
            # <<< POPRAWKA: Użyj 'detail' zamiast 'message'
            raise DatabaseException(
                detail=f"Unexpected error fetching rules: {e}"
            ) from e

        # --- Krok 4.4: Ewaluuj Reguły ---
        rule_matched = False
        matched_rule: Optional[Dict[str, Any]] = None
        now_utc = datetime.now(timezone.utc)

        print(f"Evaluating rules at time: {now_utc.isoformat()}")

        for rule in rules:
            print(
                f"Evaluating rule ID: {rule.get('id','N/A')}, Priority: {rule.get('priority','N/A')}, Type: {rule.get('rule_type','N/A')}"
            )
            current_rule_matched = False
            try:
                rule_type = rule.get("rule_type")

                if rule_type == RuleTypeEnum.TIME.value:
                    start_time = await self._parse_iso_datetime(rule.get("start_time"))
                    end_time = await self._parse_iso_datetime(rule.get("end_time"))
                    if start_time and end_time:
                        if start_time <= now_utc <= end_time:
                            print(f"Rule {rule.get('id','N/A')} (time) MATCHED")
                            current_rule_matched = True
                        else:
                            print(
                                f"Rule {rule.get('id','N/A')} (time) NOT MATCHED: Current time outside range."
                            )
                    else:
                        print(
                            f"Rule {rule.get('id','N/A')} (time) SKIPPED: Invalid or missing times."
                        )

                elif rule_type == RuleTypeEnum.CLICKS.value:
                    current_clicks = rule.get("current_clicks")
                    max_clicks = rule.get("max_clicks")
                    if isinstance(current_clicks, int) and isinstance(max_clicks, int):
                        if current_clicks < max_clicks:
                            print(
                                f"Rule {rule.get('id','N/A')} (clicks) MATCHED: {current_clicks} < {max_clicks}"
                            )
                            current_rule_matched = True
                        else:
                            print(
                                f"Rule {rule.get('id','N/A')} (clicks) NOT MATCHED: Limit reached ({current_clicks} >= {max_clicks})"
                            )
                    else:
                        print(
                            f"Rule {rule.get('id','N/A')} (clicks) SKIPPED: Invalid or missing click values."
                        )
                else:
                    print(
                        f"Rule {rule.get('id','N/A')} SKIPPED: Unknown rule type '{rule_type}'."
                    )

            except Exception as e:
                print(
                    f"ERROR evaluating rule ID {rule.get('id', 'N/A')}: {e}. Skipping rule."
                )
                traceback.print_exc()
                continue

            if current_rule_matched:
                rule_matched = True
                matched_rule = rule
                print(
                    f"Rule {matched_rule.get('id','N/A')} selected as the final match."
                )
                break

        # --- Krok 4.5: Obsłuż Wynik Ewaluacji ---
        if rule_matched and matched_rule:
            matched_rule_id = matched_rule.get("id")
            if matched_rule_id:
                try:
                    print(
                        f"Attempting to increment current clicks for matched rule ID: {matched_rule_id}"
                    )
                    await self.supabase_client.rpc(
                        "increment_rule_clicks", {"rule_uuid": str(matched_rule_id)}
                    ).execute()
                    print(
                        f"Successfully called RPC increment_rule_clicks for rule ID: {matched_rule_id}"
                    )
                except PostgrestAPIError as e:
                    print(
                        f"ERROR: Database error incrementing clicks for rule {matched_rule_id}: {getattr(e,'message','Unknown error')}. Continuing redirection."
                    )
                except Exception as e:
                    print(
                        f"ERROR: Unexpected error incrementing clicks for rule {matched_rule_id}: {e}. Continuing redirection."
                    )
                    traceback.print_exc()
            else:
                print(
                    "ERROR: Matched rule data is missing 'id'. Cannot increment rule counter."
                )

            target_type = matched_rule.get("target_type")
            target_value = matched_rule.get("target_value")

            if target_type == TargetTypeEnum.URL.value:
                print(f"Action: REDIRECT_URL to {target_value}")
                return (RedirectionAction.REDIRECT_URL, target_value)
            elif target_type == TargetTypeEnum.HTML.value:
                print(f"Action: SERVE_HTML")
                return (RedirectionAction.SERVE_HTML, target_value)
            else:
                print(
                    f"ERROR: Matched rule {matched_rule_id} has unknown target_type: {target_type}. Falling back."
                )
                return (RedirectionAction.REDIRECT_GLOBAL_FALLBACK, None)
        else:
            print("No rule matched.")
            if default_url:
                print(f"Action: REDIRECT_DEFAULT to {default_url}")
                return (RedirectionAction.REDIRECT_DEFAULT, default_url)
            else:
                print(f"Action: REDIRECT_GLOBAL_FALLBACK (no default URL defined)")
                return (RedirectionAction.REDIRECT_GLOBAL_FALLBACK, None)
