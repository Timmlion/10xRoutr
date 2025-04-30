# src/db/supabase_client.py

from supabase import create_async_client, AsyncClient
from typing import Optional

# Import application settings to get Supabase URL and keys
from src.core.config import settings

# --- Global Singleton Variables ---
# These variables will hold the single, application-wide instances of the Supabase clients.
# They are initialized to None and will be populated by `init_supabase_clients`.
supabase_service_client_instance: Optional[AsyncClient] = None
supabase_user_client_instance: Optional[AsyncClient] = None

# Flag to prevent accidental re-initialization
_clients_initialized = False


async def init_supabase_clients():
    """
    Asynchronously initializes the global Supabase client singletons (service role and anon/user role).

    This function should be called exactly once during the application startup sequence,
    typically within a FastAPI lifespan context manager. It uses the SupABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY, and SUPABASE_KEY from the application settings.
    """
    global supabase_service_client_instance, supabase_user_client_instance, _clients_initialized

    # Prevent re-initialization if called multiple times
    if _clients_initialized:
        print("Supabase clients already initialized.")
        return

    print("Initializing Supabase clients...")
    try:
        # --- Service Role Client Initialization ---
        # This client uses the service role key and has admin privileges.
        # Use it for operations requiring elevated permissions, often bypassing RLS.
        print("Creating Supabase service client instance...")
        url_svc: str = str(settings.SUPABASE_URL)
        key_svc: str = str(settings.SUPABASE_SERVICE_ROLE_KEY)
        # `create_async_client` establishes the connection pool and client object.
        supabase_service_client_instance = await create_async_client(url_svc, key_svc)
        print("Supabase service client created successfully.")

        # --- User Role (Anon Key) Client Initialization ---
        # This client uses the public anonymous key. It's used for operations
        # that rely on user authentication (e.g., RLS policies) or public data access.
        # Authentication state (JWT) is typically managed per-request or via user sessions.
        print("Creating Supabase user (anon key) client instance...")
        url_user: str = str(settings.SUPABASE_URL)
        key_user: str = str(settings.SUPABASE_KEY)  # Public Anon Key
        supabase_user_client_instance = await create_async_client(url_user, key_user)
        print("Supabase user (anon key) client created successfully.")

        _clients_initialized = True
        print("Supabase clients initialized successfully.")

    except Exception as e:
        # If client initialization fails, log the error and raise a critical exception.
        # This prevents the application from starting without essential database connectivity.
        print(f"FATAL ERROR: Failed to initialize Supabase clients: {e}")
        raise RuntimeError(f"Could not initialize Supabase clients: {e}") from e


# --- Getter Functions for Dependencies ---
# These synchronous functions provide access to the initialized client instances.
# They are designed to be used as FastAPI dependencies (via `Depends(...)`).


def get_supabase_service_client() -> AsyncClient:
    """
    Returns the initialized Supabase service client singleton instance.

    Raises a RuntimeError if accessed before `init_supabase_clients` has been successfully called.
    """
    if supabase_service_client_instance is None:
        # This state indicates a programming error (calling get_* before lifespan initialization).
        print("ERROR: Supabase service client accessed before initialization!")
        raise RuntimeError(
            "Supabase service client not initialized. Ensure lifespan context is used."
        )
    return supabase_service_client_instance


def get_supabase_user_client() -> AsyncClient:
    """
    Returns the initialized Supabase user (anon key) client singleton instance.

    Raises a RuntimeError if accessed before `init_supabase_clients` has been successfully called.
    """
    if supabase_user_client_instance is None:
        print("ERROR: Supabase user client accessed before initialization!")
        raise RuntimeError(
            "Supabase user client not initialized. Ensure lifespan context is used."
        )
    return supabase_user_client_instance
