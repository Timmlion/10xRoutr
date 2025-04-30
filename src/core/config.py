# src/core/config.py

import os
from pathlib import Path  # For constructing file paths reliably
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)  # Core components for settings management
from pydantic import HttpUrl, Field  # For URL validation and defining required fields
from typing import Literal  # For defining allowed string values (e.g., logging levels)

# --- .env File Path Configuration ---
# Determine the path to the .env file, assuming it's in the project root (one level above 'src')
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# Optional: Check if the .env file exists for easier debugging
if not ENV_PATH.is_file():
    print(f"WARNING: .env file not found at {ENV_PATH}")
    print("         Application settings will rely solely on environment variables.")


class Settings(BaseSettings):
    """
    Defines and loads application settings from environment variables and/or a .env file.
    Leverages pydantic-settings for automatic loading, type casting, and validation.
    """

    # --- General Application Settings ---
    # Basic application identifiers and configurations with default values.
    APP_NAME: str = "routr"
    APP_VERSION: str = "0.1.0"
    # Example of using Literal to restrict possible values for a setting.
    LOGGING_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Required Settings ---
    # These settings MUST be provided either in the .env file or as environment variables.
    # The `Field(..., description="...")` syntax indicates they are required.
    # HttpUrl ensures the value is a valid HTTP/HTTPS URL.
    GLOBAL_FALLBACK_URL: HttpUrl = Field(
        ...,  # Indicates this field is required
        description="Default URL to redirect to if no rule matches and no link-specific default exists.",
    )
    # Supabase connection details.
    SUPABASE_URL: str = Field(..., description="URL of your Supabase project.")
    SUPABASE_KEY: str = Field(
        ..., description="Anon key for your Supabase project (public)."
    )
    # IMPORTANT: The service role key is highly sensitive and should be kept secret.
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        ..., description="Service role key for your Supabase project (secret!)."
    )

    # --- Pydantic Settings Configuration (Pydantic v2+) ---
    model_config = SettingsConfigDict(
        # Specify the path to the .env file to load variables from.
        env_file=str(ENV_PATH),
        # Define the encoding of the .env file.
        env_file_encoding="utf-8",
        # Ignore any environment variables that don't match fields defined in this Settings class.
        extra="ignore",
        # Make environment variable names case-insensitive during loading.
        case_sensitive=False,
    )


# --- Instantiate Settings ---
# Create a single, global instance of the Settings class.
# This instance will be imported and used throughout the application.
# The instantiation automatically triggers loading and validation based on `model_config`.
settings = Settings()

# --- Settings Loading Verification (for Development/Debugging) ---
# Print loaded settings to confirm they are read correctly.
# This block includes a try-except to catch validation errors during instantiation.
# CRITICAL: Avoid logging sensitive information like SUPABASE_SERVICE_ROLE_KEY in production environments.
print("--- Loading Application Settings ---")
try:
    # Re-instantiate within try block to catch validation errors if any occurred
    # (Although the initial instantiation above would have already raised them)
    verified_settings = (
        Settings()
    )  # Use a different variable name to avoid confusion if needed
    print("Application settings loaded successfully:")
    print(f"  APP_NAME: {verified_settings.APP_NAME}")
    print(f"  APP_VERSION: {verified_settings.APP_VERSION}")
    print(f"  LOGGING_LEVEL: {verified_settings.LOGGING_LEVEL}")
    print(f"  GLOBAL_FALLBACK_URL: {verified_settings.GLOBAL_FALLBACK_URL}")
    print(f"  SUPABASE_URL: {verified_settings.SUPABASE_URL}")
    # Obscure sensitive keys when logging, even public ones sometimes.
    print(f"  SUPABASE_KEY: {verified_settings.SUPABASE_KEY[:5]}... (Public Anon Key)")
    # Example of how to explicitly NOT log a secret.
    print(f"  SUPABASE_SERVICE_ROLE_KEY: [SECRET - NOT LOGGED]")
    print("--- Settings Loaded ---")
except Exception as e:
    # Log fatal errors if settings fail to load or validate.
    print(f"FATAL ERROR: Failed to load or validate application settings: {e}")
    # In a real application, you might want to exit here or raise the exception
    # raise e
    # exit(1)

# Ensure the globally used 'settings' variable holds the validated settings
settings = verified_settings
