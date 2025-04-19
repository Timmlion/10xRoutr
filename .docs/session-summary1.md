# Podsumowanie Projektu "routr" (MVP) - Część 1/N

## A. Wprowadzenie i Cel Projektu

**Nazwa Projektu:** routr (MVP)

**Główny Problem:** Aplikacja rozwiązuje problem ograniczonego, statycznego udostępniania treści w kampaniach marketingowych. Umożliwia tworzenie inteligentnych linków, które dynamicznie przekierowują użytkowników końcowych.

**Docelowy Użytkownik (MVP):** Influencerzy i marketerzy potrzebujący elastycznego zarządzania linkami w kampaniach (np. ograniczonych czasowo lub ilościowo).

**Podstawowa Funkcjonalność:**

1.  Generowanie unikalnych linków (`routr.app/alias`).
2.  Definiowanie reguł przekierowania dla każdego linku opartych na:
    - **Czasie:** Okres ważności (data/godzina początkowa i końcowa).
    - **Ilości kliknięć:** Maksymalna liczba przekierowań dla danej reguły.
3.  Ustawianie priorytetów dla reguł (niższy numer = wyższy priorytet).
4.  Określanie celu dla każdej reguły:
    - Zewnętrzny adres URL.
    - Niestandardowa zawartość HTML (wklejana przez użytkownika).
5.  Opcjonalne ustawienie domyślnego URL przekierowania dla linku (gdy żadna reguła nie pasuje).
6.  Publiczny mechanizm przekierowania, który ewaluuje reguły i kieruje użytkownika końcowego.
7.  System autentykacji użytkowników (zarządzających linkami).
8.  Podstawowy panel zarządzania (webowy) do tworzenia, edycji, usuwania linków i reguł oraz przeglądania statystyk.
9.  Podstawowe statystyki: całkowita liczba kliknięć linku i liczba kliknięć dla każdej reguły/celu.

**Zakres MVP (Co NIE wchodzi):** Zaawansowane reguły (geolokalizacja, urządzenie), zaawansowana analityka, role użytkowników, funkcje premium, integracje, zaawansowane zabezpieczenia (boty, rate limiting - poza podstawowym), cache'owanie, edycja aliasu po utworzeniu.

## B. Stos Technologiczny

- **Backend:**
  - Język: **Python 3.x**
  - Framework: **FastAPI**
  - Serwer: **Uvicorn**
  - Architektura: **Monolit** (FastAPI serwuje logikę backendu i HTML frontendu).
- **Frontend (Panel Zarządzania):**
  - Interakcja: **HTMX** (ładowanie fragmentów bez przeładowania strony, przez CDN).
  - UI/CSS: **Bootstrap 5** (przez CDN).
  - Komponenty JS: **Flatpickr** (dla date pickera, przez CDN).
  - Templating: **Jinja2** (renderowanie po stronie serwera w FastAPI).
- **Baza Danych i Autentykacja:**
  - Platforma: **Supabase (BaaS)**
  - Baza Danych: **PostgreSQL** (w ramach Supabase)
  - Uwierzytelnianie: **Supabase Auth**
  - Interakcja z DB/Auth (Python): Biblioteka **`supabase-py`** (wersja async `supabase_py_async`).
- **Infrastruktura:**
  - Konteneryzacja: **Docker**
  - Hosting: Własny **VPS**
  - Zarządzanie Wdrożeniem: **Coolify** (planowane)
- **Narzędzia Developerskie:**
  - Zarządzanie zależnościami: `pip` z `requirements.txt` (lub `pyproject.toml`).
  - Środowisko wirtualne: `venv`.
  - Linter/Formatter: `Ruff` lub `Black`/`Flake8`.
  - Zmienne środowiskowe: `.env` plik (z `python-dotenv`) i konfiguracja w Coolify.

## C. Konfiguracja Środowiska VS Code

- Zalecane rozszerzenia: Python (Microsoft), Ruff/Black/Flake8, Jinja, HTMX Support, Docker, DotENV.
- Skonfigurowano `settings.json` do użycia wybranego interpretera z `.venv`, lintera (np. Ruff) i formattera (np. Black) z formatowaniem przy zapisie.
- Skonfigurowano `launch.json` do uruchamiania i debugowania aplikacji FastAPI z Uvicorn (`module: uvicorn`, `args: ["main:app", "--reload", ...]`), wczytując zmienne z `.env`.
- Użyto `pip` do instalacji zależności (FastAPI, Uvicorn, Jinja2, Supabase, python-dotenv), rozwiązując problem z `uvicorn[standard]` w Zsh (`pip install "uvicorn[standard]"`).
- Utworzono plik `.env.example` i `.gitignore`.

# Podsumowanie Projektu "routr" (MVP) - Część 2/N

## D. Schemat Bazy Danych PostgreSQL (w Supabase)

**Cel:** Przechowywanie danych o linkach, regułach i podstawowych statystykach kliknięć w sposób wydajny i bezpieczny, z wykorzystaniem RLS do izolacji danych użytkowników.

**Główne Tabele (w schemacie `public`):**

1.  **`routr_links`**: Przechowuje informacje o każdym unikalnym linku routr.

    - `id` (UUID, PK, `gen_random_uuid()`): Identyfikator linku.
    - `user_id` (UUID, NOT NULL, FK do `auth.users(id)`): Identyfikator właściciela linku. _Uwaga: `ON DELETE CASCADE` musi być obsłużone przez Supabase Edge Function, nie bezpośrednio w definicji FK._
    - `alias` (TEXT, NOT NULL, UNIQUE): Unikalna ścieżka linku (np. "moja-kampania").
      - Ograniczenie `CHECK`: `alias ~ '^[a-z0-9-]+$'`, `length(alias) >= 3`, `length(alias) <= 64`.
    - `default_url` (TEXT, NULL): Opcjonalny URL przekierowania, gdy żadna reguła nie pasuje.
      - Ograniczenie `CHECK`: Podstawowa walidacja formatu URL (`http://` lub `https://`) jeśli nie jest `NULL`.
    - `total_clicks` (BIGINT, NOT NULL, DEFAULT 0): Całkowita liczba kliknięć tego aliasu. Inkrementowany atomowo.
    - `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT `now()`): Czas utworzenia.
    - `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT `now()`): Czas ostatniej modyfikacji (aktualizowany przez trigger).

2.  **`routing_rules`**: Przechowuje reguły przekierowania dla poszczególnych linków.
    - `id` (UUID, PK, `gen_random_uuid()`): Identyfikator reguły.
    - `link_id` (UUID, NOT NULL, FK do `routr_links(id) ON DELETE CASCADE`): Identyfikator linku nadrzędnego. Usunięcie linku usuwa jego reguły.
    - `priority` (SMALLINT, NOT NULL): Priorytet wykonania reguły (niższa liczba = wyższy priorytet). Musi być dodatni (`> 0`).
      - Ograniczenie `UNIQUE (link_id, priority)`: Zapewnia unikalność priorytetu w ramach jednego linku.
    - `rule_type` (public.rule_type_enum, NOT NULL): Typ warunku reguły ('time' lub 'clicks').
    - `target_type` (public.target_type_enum, NOT NULL): Typ celu przekierowania ('url' lub 'html').
    - `target_value` (TEXT, NOT NULL): Wartość celu (URL lub kod HTML).
      - Ograniczenie `CHECK`: Podstawowa walidacja formatu URL, jeśli `target_type = 'url'`.
      - _Uwaga: Ograniczenie CHECK dla długości HTML jest planowane, ale limit nie został jeszcze ustalony._
    - `start_time` (TIMESTAMPTZ, NULL): Czas rozpoczęcia ważności (wymagany dla `rule_type = 'time'`). Przechowywany w UTC.
    - `end_time` (TIMESTAMPTZ, NULL): Czas zakończenia ważności (wymagany dla `rule_type = 'time'`). Przechowywany w UTC.
    - `max_clicks` (BIGINT, NULL): Maksymalna liczba kliknięć (wymagana i musi być `> 0` dla `rule_type = 'clicks'`).
    - `current_clicks` (BIGINT, NOT NULL, DEFAULT 0): Aktualna liczba kliknięć dla tej konkretnej reguły. Inkrementowany atomowo.
    - `created_at` (TIMESTAMPTZ, NOT NULL, DEFAULT `now()`).
    - `updated_at` (TIMESTAMPTZ, NOT NULL, DEFAULT `now()`).
    - Ograniczenia `CHECK`: Zapewniają, że `start_time`/`end_time` są ustawione dla typu 'time', a `max_clicks` dla typu 'clicks'.

**Typy Niestandardowe (ENUM):**

- `public.rule_type_enum`: (`'time'`, `'clicks'`)
- `public.target_type_enum`: (`'url'`, `'html'`)

**Funkcje i Wyzwalacze (Triggers):**

- `public.handle_updated_at()`: Funkcja PostgreSQL automatycznie ustawiająca `updated_at = now()` przy aktualizacji wiersza.
- Wyzwalacze `BEFORE UPDATE` na tabelach `routr_links` i `routing_rules` wywołujące `handle_updated_at()`.
- **Funkcje RPC (do inkrementacji):**
  - `public.increment_link_clicks(link_uuid uuid)`: Atomowo wykonuje `UPDATE routr_links SET total_clicks = total_clicks + 1 WHERE id = link_uuid;`.
  - `public.increment_rule_clicks(rule_uuid uuid)`: Atomowo wykonuje `UPDATE routing_rules SET current_clicks = current_clicks + 1 WHERE id = rule_uuid;`.
  - Obie funkcje zdefiniowane jako `VOLATILE`, `SECURITY DEFINER` z nadanymi uprawnieniami `EXECUTE` dla roli `service_role`.

**Indeksy:**

- Automatyczne: Na kluczach głównych (`id`) i obcych (`user_id`, `link_id`).
- Dodatkowe (jawnie zdefiniowane):
  - `idx_routr_links_alias ON public.routr_links(alias)`: Dla szybkiego wyszukiwania linku po aliasie (kluczowe dla przekierowań).
  - `idx_routing_rules_link_id_priority ON public.routing_rules(link_id, priority)`: Dla szybkiego pobierania i sortowania reguł dla danego linku (kluczowe dla przekierowań i wyświetlania listy reguł).

**Bezpieczeństwo na Poziomie Wierszy (RLS):**

- Włączone (`ENABLE ROW LEVEL SECURITY`) dla tabel `routr_links` i `routing_rules`.
- **Polityki:**
  - Zdefiniowano polityki `FOR ALL` (SELECT, INSERT, UPDATE, DELETE) dla obu tabel.
  - Warunek `USING`: `auth.uid() = user_id` (dla `routr_links`) lub `link_id IN (SELECT id FROM public.routr_links WHERE auth.uid() = user_id)` (dla `routing_rules`). Ogranicza dostęp do danych tylko dla ich właściciela, gdy używany jest token JWT użytkownika.
  - Warunek `WITH CHECK`: Identyczny jak `USING`, zapobiega przypisaniu danych do innego użytkownika podczas `INSERT` lub `UPDATE`.
- **Dostęp `service_role`:** Logika backendu obsługująca publiczne przekierowania (`/{alias_path:path}`) musi używać klienta Supabase z kluczem `service_role`, który **omija** polityki RLS, aby móc odczytać dowolny link/regułę i zaktualizować liczniki. Klucz `service_role` ma również nadane uprawnienia `EXECUTE` na funkcje RPC inkrementujące liczniki.

**Nierozwiązane Kwestie Dotyczące Bazy Danych:**

1.  **Limit Rozmiaru HTML:** Dokładny limit dla `routing_rules.target_value` typu 'html' nie został ustalony. Należy zdefiniować limit i ewentualnie dodać ograniczenie `CHECK` w migracji.
2.  **Kaskada Usuwania Użytkownika:** Implementacja logiki w Supabase Edge Function do usuwania linków po usunięciu użytkownika z `auth.users` jest zaplanowana, ale nie zaimplementowana.

# Podsumowanie Projektu "routr" (MVP) - Część 3/N

## E. Plan API REST (Interfejs Zarządzania)

Zdefiniowano API RESTful do zarządzania linkami i regułami przez uwierzytelnionych użytkowników. Główne zasoby i endpointy:

1.  **Zasób: Linki (`/links`)** - Odpowiada `routr_links`.

    - `POST /links`: **Utwórz Link** (przyjmuje `LinkCreate`, zwraca `LinkResponse`, status 201). Wymaga autentykacji.
    - `GET /links`: **Pobierz Listę Linków** (przyjmuje parametry paginacji `page`, `page_size`, zwraca `PaginatedLinkResponse`, status 200). Wymaga autentykacji. _Może opcjonalnie zwracać fragment HTML dla HTMX._
    - `GET /links/{link_id}`: **Pobierz Link** (przyjmuje `link_id` z ścieżki, zwraca `LinkResponse`, status 200). Wymaga autentykacji i własności linku (RLS).
    - `PATCH /links/{link_id}`: **Zaktualizuj Link** (przyjmuje `link_id` z ścieżki i `LinkUpdate` w ciele - tylko `default_url` w MVP, zwraca `LinkResponse`, status 200). Wymaga autentykacji i własności linku (RLS).
    - `DELETE /links/{link_id}`: **Usuń Link** (przyjmuje `link_id` z ścieżki, zwraca status 204). Wymaga autentykacji i własności linku (RLS). Usuwa też powiązane reguły (kaskada DB).

2.  **Zasób: Reguły (`/links/{link_id}/rules`)** - Odpowiada `routing_rules`, zagnieżdżony pod linkiem.

    - `POST /links/{link_id}/rules`: **Utwórz Regułę** (przyjmuje `link_id` z ścieżki i `RuleCreate` w ciele, zwraca `RuleResponse`, status 201). Wymaga autentykacji i własności `link_id` (sprawdzane w serwisie + RLS).
    - `GET /links/{link_id}/rules`: **Pobierz Listę Reguł** (przyjmuje `link_id` z ścieżki, zwraca `List[RuleResponse]` posortowaną wg `priority`, status 200). Wymaga autentykacji i własności `link_id` (sprawdzane w serwisie + RLS). _Może opcjonalnie zwracać fragment HTML dla HTMX._
    - `GET /links/{link_id}/rules/{rule_id}`: **Pobierz Regułę** (przyjmuje `link_id` i `rule_id` z ścieżki, zwraca `RuleResponse`, status 200). Wymaga autentykacji i własności `link_id` (RLS).
    - `PATCH /links/{link_id}/rules/{rule_id}`: **Zaktualizuj Regułę** (przyjmuje `link_id`, `rule_id` z ścieżki i `RuleUpdate` w ciele, zwraca `RuleResponse`, status 200). Wymaga autentykacji i własności `link_id` (sprawdzane w serwisie + RLS).
    - `DELETE /links/{link_id}/rules/{rule_id}`: **Usuń Regułę** (przyjmuje `link_id`, `rule_id` z ścieżki, zwraca status 204). Wymaga autentykacji i własności `link_id` (sprawdzane w serwisie + RLS).

3.  **Zasób: Statystyki (`/links/{link_id}/stats`)** - Dane pochodne.

    - `GET /links/{link_id}/stats`: **Pobierz Statystyki Linku** (przyjmuje `link_id` z ścieżki, zwraca `LinkStatsResponse`, status 200). Wymaga autentykacji i własności `link_id` (RLS).

4.  **Zasób: Uwierzytelnianie (`/auth`)** - Interakcja z Supabase Auth.
    - `POST /auth/login`: **Logowanie** (przyjmuje `UserLogin`, zwraca `TokenResponse`, status 200). Publiczny.
    - `POST /auth/register`: **Rejestracja** (przyjmuje `UserRegister`, zwraca `UserRegistrationResponse`, status 201). Publiczny (opcjonalny, może być realizowany przez klienta).

**Uwierzytelnianie/Autoryzacja API:**

- Użycie **JWT Bearer Token** (wydawanych przez Supabase Auth) w nagłówku `Authorization`.
- Zależność FastAPI (`deps.get_current_user` / `deps.get_current_user_id`) weryfikuje token i dostarcza ID użytkownika.
- Autoryzacja na poziomie danych jest wymuszana głównie przez **RLS** w bazie danych, bazując na `auth.uid()` powiązanym z tokenem JWT. Serwisy dodatkowo weryfikują własność przed operacjami modyfikacji/usunięcia dla lepszej obsługi błędów (404).

**Walidacja:**

- FastAPI automatycznie waliduje typy i podstawowe ograniczenia (np. `min_length`, `max_length`, format `EmailStr`, `HttpUrl`) zdefiniowane w modelach Pydantic DTO (`schemas/`). Zwraca `422 Unprocessable Entity` w razie błędu.
- Niestandardowe walidatory Pydantic (`@field_validator`, `@model_validator`) w DTO (`LinkCreate`, `RuleCreate`, `RuleUpdate`) sprawdzają bardziej złożone reguły (np. format aliasu, warunkowe wymagania pól reguł).
- Warstwa serwisowa wykonuje dodatkowe walidacje logiki biznesowej (np. spójność danych przy `PATCH` dla `RuleUpdate`).
- Ograniczenia bazy danych (`UNIQUE`, `CHECK`) stanowią ostateczną warstwę walidacji.

## F. Plan API (Publiczne Przekierowanie)

Zdefiniowano również oddzielny plan dla publicznego endpointu przekierowania.

- **Endpoint:** `GET /{alias_path:path}`
- **Opis:** Główny punkt wejścia aplikacji. Przechwytuje alias, znajduje link, ewaluuje reguły (czas, kliknięcia) wg priorytetu, inkrementuje liczniki (linku i reguły - atomowo przez RPC) i wykonuje akcję:
  - Przekierowanie `302 Found` na `target_value` (jeśli `target_type`='url').
  - Zwrócenie `200 OK` z `Content-Type: text/html` i `target_value` (jeśli `target_type`='html').
  - Przekierowanie `302 Found` na `default_url` linku (jeśli żadna reguła nie pasuje, a `default_url` istnieje).
  - Przekierowanie `302 Found` na globalny URL zapasowy (jeśli żadna reguła nie pasuje i brak `default_url`).
- **Uwierzytelnianie:** Brak (publiczny).
- **Autoryzacja (Dostęp DB):** Logika backendu **musi** używać klienta Supabase z kluczem **`service_role`**, aby ominąć RLS i móc odczytać dowolny link/regułę oraz inkrementować liczniki.
- **Obsługa Błędów:** Zwraca `404 Not Found`, jeśli alias nie istnieje. Zwraca `500 Internal Server Error` dla błędów DB lub logiki (z logowaniem po stronie serwera). Błędy inkrementacji liczników są logowane, ale nie powinny przerywać procesu przekierowania.
- **Bezpieczeństwo:** Podatność na XSS (przy `target_type='html'`) i Open Redirect zależy od walidacji przy tworzeniu/edycji reguł. Wymaga Rate Limitingu.

## G. Struktura Aplikacji i Stan Implementacji

- **Struktura:** Zdefiniowano strukturę folderów i plików (`src/`, `api/`, `core/`, `db/`, `models/`, `schemas/`, `services/`, `static/`, `templates/`, `tests/`, `supabase/migrations/`, `main.py`, `Dockerfile`, etc.).
- **Modele Pydantic (`src/schemas/`):** Zdefiniowano modele DTO dla żądań i odpowiedzi API (`LinkCreate`, `LinkUpdate`, `LinkResponse`, `PaginatedLinkResponse`, `RuleCreate`, `RuleUpdate`, `RuleResponse`, `UserLogin`, `UserRegister`, `TokenResponse`, `UserRegistrationResponse`, `LinkStatsResponse`, `TargetClickStat`, `PaginationParams`) oraz Enumy (`RuleTypeEnum`, `TargetTypeEnum`).
- **Serwisy (`src/services/`):**
  - `AuthService`: Zaimplementowano metody `login_user` i `register_user` wraz z obsługą błędów Supabase Auth.
  - `LinkService`: Zaimplementowano metody `create_link`, `get_link_by_id`, `get_links_paginated`, `update_link`, `delete_link`, `get_link_statistics` wraz z weryfikacją własności (gdzie potrzebne) i obsługą błędów DB/logiki.
  - `RuleService`: Zaimplementowano metody `add_rule_to_link`, `get_rules_for_link`, `get_rule_details`, `update_rule`, `delete_rule` wraz z weryfikacją własności linku nadrzędnego i obsługą błędów DB/logiki (w tym konfliktu priorytetu).
  - `RedirectionService`: Zaimplementowano metodę `process_redirection` (włącznie z logiką ewaluacji reguł i wywołaniami RPC do inkrementacji liczników), która zwraca `RedirectionAction`. Wymaga klienta `service_role`.
  - Zdefiniowano niestandardowe wyjątki (`ServiceException`, `DatabaseException`, `NotFoundException`, `ParentLinkNotFoundException`, `AliasConflictException`, `PriorityConflictException`, `AuthenticationFailedException`, `EmailExistsException`, `PasswordPolicyException`, `ValidationException`).
- **Endpointy API (`src/api/v1/endpoints/`):**
  - `links.py`: Zaimplementowano **wszystkie** endpointy CRUD dla `/links` oraz endpoint `GET /links/{link_id}/stats`.
  - `rules.py`: Zaimplementowano **wszystkie** endpointy CRUD dla `/links/{link_id}/rules`.
  - `auth.py`: Zaimplementowano endpointy `/auth/login` i (opcjonalny) `/auth/register`.
  - `stats.py`: Endpoint statystyk został zintegrowany w `links.py`.
- **Router API (`src/api/v1/api.py`):** Skonfigurowano dołączenie routerów `links` i `rules`.
- **Zależności (`src/api/deps.py`):** Zaimplementowano zależności dla uwierzytelniania (`get_current_user`, `get_current_user_id`), paginacji (`pagination_dependency`) oraz wstrzykiwania serwisów (`get_link_service`, `get_rule_service`, `get_auth_service`, `get_redirection_service`). _Uwaga: Wymaga doprecyzowania/implementacji logiki rozróżniania klientów Supabase (user vs service_role)._
- **Aplikacja Główna (`src/main.py`):** Zaimplementowano inicjalizację aplikacji FastAPI, dołączenie routera API v1, konfigurację szablonów Jinja2 oraz implementację publicznego endpointu przekierowania `/{alias_path:path}` wywołującego `RedirectionService`.
