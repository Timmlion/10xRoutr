# src/db/supabase_client.py

# Zmieniamy import - nie potrzebujemy create_client, tylko AsyncClient
from supabase import AsyncClient
from functools import lru_cache

from src.core.config import settings


@lru_cache(maxsize=None)
def get_supabase_service_client() -> AsyncClient:
    """
    Creates and returns a Supabase AsyncClient instance configured with the SERVICE_ROLE_KEY.
    This client bypasses RLS policies. Use with caution.
    Uses lru_cache to act as a singleton.
    """
    print("Creating Supabase service client instance (AsyncClient)...")  # Logowanie MVP
    try:
        # Bezpośrednio tworzymy instancję AsyncClient
        client = AsyncClient(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        print(
            "Supabase service client (AsyncClient) created successfully."
        )  # Logowanie MVP
        return client
    except Exception as e:
        print(f"FATAL ERROR: Failed to create Supabase service client: {e}")
        raise RuntimeError(f"Could not initialize Supabase service client: {e}") from e


@lru_cache(maxsize=None)
def get_supabase_user_client() -> AsyncClient:
    """
    Creates and returns a Supabase AsyncClient instance configured with the ANON_KEY.
    This client respects RLS policies based on the JWT provided in the request headers.
    Uses lru_cache to act as a singleton.
    """
    print(
        "Creating Supabase user (anon key) client instance (AsyncClient)..."
    )  # Logowanie MVP
    try:
        # Bezpośrednio tworzymy instancję AsyncClient używając klucza anon
        client = AsyncClient(
            settings.SUPABASE_URL, settings.SUPABASE_KEY  # Używamy klucza anon (public)
        )
        print(
            "Supabase user (anon key) client (AsyncClient) created successfully."
        )  # Logowanie MVP
        return client
    except Exception as e:
        print(f"FATAL ERROR: Failed to create Supabase user client: {e}")
        raise RuntimeError(f"Could not initialize Supabase user client: {e}") from e
