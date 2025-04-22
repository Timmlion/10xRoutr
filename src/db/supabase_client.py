# src/db/supabase_client.py (Revised for Async Initialization)

from supabase import create_async_client, AsyncClient
from typing import Optional

from src.core.config import settings

# --- Globalne zmienne dla singletonów klientów ---
# Zaczynają jako None, zostaną zainicjalizowane podczas startu aplikacji
supabase_service_client_instance: Optional[AsyncClient] = None
supabase_user_client_instance: Optional[AsyncClient] = None

# Flaga zapobiegająca wielokrotnej inicjalizacji (na wszelki wypadek)
_clients_initialized = False


async def init_supabase_clients():
    """
    Asynchronously initializes the Supabase client singletons.
    Should be called once during application startup (e.g., using lifespan).
    """
    global supabase_service_client_instance, supabase_user_client_instance, _clients_initialized
    if _clients_initialized:
        print("Supabase clients already initialized.")
        return

    print("Initializing Supabase clients...")
    try:
        # --- Inicjalizacja klienta serwisowego ---
        print("Creating Supabase service client instance...")
        url_svc: str = str(settings.SUPABASE_URL)
        key_svc: str = str(settings.SUPABASE_SERVICE_ROLE_KEY)
        supabase_service_client_instance = await create_async_client(
            url_svc, key_svc
        )  # <<< Używamy await
        print("Supabase service client created successfully.")

        # --- Inicjalizacja klienta użytkownika ---
        print("Creating Supabase user (anon key) client instance...")
        url_user: str = str(settings.SUPABASE_URL)
        key_user: str = str(settings.SUPABASE_KEY)  # Klucz ANON
        supabase_user_client_instance = await create_async_client(
            url_user, key_user
        )  # <<< Używamy await
        print("Supabase user (anon key) client created successfully.")

        _clients_initialized = True
        print("Supabase clients initialized successfully.")

    except Exception as e:
        print(f"FATAL ERROR: Failed to initialize Supabase clients: {e}")
        # Można tu rzucić wyjątek, aby zatrzymać start aplikacji, jeśli połączenie jest krytyczne
        raise RuntimeError(f"Could not initialize Supabase clients: {e}") from e


# --- Funkcje zwracające zainicjalizowane instancje (NIE async) ---
# Te funkcje będą używane przez zależności FastAPI (Depends)
def get_supabase_service_client() -> AsyncClient:
    """Returns the initialized Supabase service client singleton."""
    if supabase_service_client_instance is None:
        # To nie powinno się zdarzyć, jeśli init_supabase_clients() zostało wywołane poprawnie
        print("ERROR: Supabase service client accessed before initialization!")
        raise RuntimeError("Supabase service client not initialized.")
    return supabase_service_client_instance


def get_supabase_user_client() -> AsyncClient:
    """Returns the initialized Supabase user client singleton."""
    if supabase_user_client_instance is None:
        print("ERROR: Supabase user client accessed before initialization!")
        raise RuntimeError("Supabase user client not initialized.")
    return supabase_user_client_instance
