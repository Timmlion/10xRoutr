# Podsumowanie Stacku Technologicznego - routr (MVP)

## 1. Backend
*   **Język:** Python
*   **Framework Webowy:** FastAPI
*   **Serwer Aplikacji (w Dockerze):** Uvicorn
*   **Podejście:** Monolit (FastAPI serwuje zarówno logikę backendu, jak i HTML frontendu).

## 2. Frontend
*   **Biblioteka Interakcji:** HTMX (do dynamicznego ładowania fragmentów HTML bez przeładowania strony, dołączana przez CDN).
*   **Framework CSS / Komponenty UI:** Bootstrap 5 (dołączany przez CDN).
*   **Komponent Datepicker:** Flatpickr (dołączany przez CDN, zintegrowany z Bootstrap).
*   **Templating Engine:** Jinja2 (do renderowania HTML po stronie serwera w FastAPI).
*   **Zależności Frontendowe:** Zarządzane głównie przez CDN w celu uproszczenia procesu budowania w MVP.

## 3. Baza Danych i Autentykacja
*   **Platforma BaaS:** Supabase
*   **Baza Danych:** PostgreSQL (w ramach Supabase)
*   **Uwierzytelnianie:** Supabase Auth
*   **Biblioteka Python do Interakcji:** `supabase-py`

## 4. Infrastruktura i Wdrożenie
*   **Konteneryzacja:** Docker
*   **Hosting:** Własny VPS
*   **Platforma Zarządzania Wdrożeniem:** Coolify
*   **Konfiguracja i Sekrety:** Zmienne środowiskowe (zarządzane przez `.env` lokalnie i Coolify na produkcji).

## 5. Narzędzia Developerskie (Zalecane)
*   **Linter / Formatter:** Black, Flake8 (lub Ruff) do utrzymania jakości i spójności kodu.
*   **Debugger:** Standardowy debugger Pythona (pdb lub w IDE).

## 6. Obsługa Plików Statycznych
*   FastAPI będzie skonfigurowane do serwowania niezbędnych lokalnych plików statycznych (jeśli powstaną, np. własne CSS/JS, obrazki), chociaż główne biblioteki FE będą ładowane przez CDN.