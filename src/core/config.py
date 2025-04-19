# src/core/config.py

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import HttpUrl, Field  # Używamy HttpUrl do walidacji URL
from typing import Literal  # Do określenia np. LOGGING_LEVEL

# Określenie ścieżki do pliku .env
# Zakładamy, że plik .env znajduje się w głównym folderze projektu,
# czyli jeden poziom nad folderem 'src'
ENV_PATH = Path(__file__).parent.parent.parent / ".env"

# Sprawdzenie, czy plik .env istnieje (opcjonalne, ale pomocne przy debugowaniu)
if not ENV_PATH.is_file():
    print(f"WARNING: .env file not found at {ENV_PATH}")
    print("         Application settings will rely solely on environment variables.")


class Settings(BaseSettings):
    """
    Loads and validates application settings from environment variables and/or .env file.
    Uses pydantic-settings for automatic loading and validation.
    """

    # --- General Application Settings ---
    APP_NAME: str = "routr"
    APP_VERSION: str = "0.1.0"
    # Przykład opcjonalnego ustawienia z wartością domyślną
    LOGGING_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Required Settings (must be present in .env or environment) ---
    # Walidacja URL za pomocą Pydantic
    GLOBAL_FALLBACK_URL: HttpUrl = Field(
        ...,
        description="Default URL to redirect to if no rule matches and no link-specific default exists.",
    )
    SUPABASE_URL: str = Field(..., description="URL of your Supabase project.")
    SUPABASE_KEY: str = Field(
        ..., description="Anon key for your Supabase project (public)."
    )
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        ..., description="Service role key for your Supabase project (secret!)."
    )

    # --- Konfiguracja Pydantic Settings (Pydantic v2+) ---
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),  # Ścieżka do pliku .env
        env_file_encoding="utf-8",  # Kodowanie pliku .env
        extra="ignore",  # Ignoruj dodatkowe zmienne w .env lub środowisku
        case_sensitive=False,  # Nazwy zmiennych nie są wrażliwe na wielkość liter
    )


# Utworzenie jednej instancji ustawień, która będzie importowana w innych modułach
settings = Settings()

# Logowanie (print dla MVP) załadowanych wartości dla weryfikacji
# Pamiętaj, aby NIE logować sekretów (SUPABASE_SERVICE_ROLE_KEY) w środowisku produkcyjnym!
print("--- Loading Application Settings ---")
try:
    # Wywołanie konstruktora ponownie w try-except, aby złapać błędy walidacji Pydantic
    settings = Settings()
    print("Application settings loaded successfully:")
    print(f"  APP_NAME: {settings.APP_NAME}")
    print(f"  APP_VERSION: {settings.APP_VERSION}")
    print(f"  LOGGING_LEVEL: {settings.LOGGING_LEVEL}")
    print(f"  GLOBAL_FALLBACK_URL: {settings.GLOBAL_FALLBACK_URL}")
    print(f"  SUPABASE_URL: {settings.SUPABASE_URL}")
    print(
        f"  SUPABASE_KEY: {settings.SUPABASE_KEY[:5]}... (Public Anon Key)"
    )  # Pokaż tylko część klucza publicznego
    # print(f"  SUPABASE_SERVICE_ROLE_KEY: SECRET") # NIGDY NIE LOGUJ W PRODUKCJI!
    print("--- Settings Loaded ---")
except Exception as e:
    print(f"FATAL ERROR: Failed to load or validate application settings: {e}")
    # W bardziej zaawansowanej aplikacji można by tu zakończyć działanie programu
    # exit(1)
