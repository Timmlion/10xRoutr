# Service Implementation Plan: LinkService

## 1. Przegląd serwisu

`LinkService` jest odpowiedzialny za zarządzanie logiką biznesową związaną z zasobami `routr_links`. Obejmuje to tworzenie, odczytywanie (pojedyncze i listy paginowane), aktualizowanie (ograniczone do `default_url` w MVP) oraz usuwanie linków. Serwis operuje w kontekście uwierzytelnionego użytkownika, wykorzystując jego ID do interakcji z bazą danych i polegając na mechanizmach RLS (Row Level Security) do zapewnienia autoryzacji na poziomie wierszy. Dodatkowo, udostępnia metodę do pobierania zagregowanych statystyk dla konkretnego linku.

## 2. Szczegóły wejścia

- **Rodzaj danych:** Obiekty Pydantic DTO dla tworzenia (`LinkCreate`) i aktualizacji (`LinkUpdate`), identyfikatory UUID dla użytkownika (`user_id`) i linku (`link_id`), parametry paginacji (`page`, `page_size`).
- **Wymagane dane:**
  - Dla `create_link`: Obiekt `LinkCreate`, `user_id`.
  - Dla `get_links_paginated`: `user_id`, `page`, `page_size`.
  - Dla `get_link_by_id`: `link_id`, `user_id`.
  - Dla `update_link`: `link_id`, Obiekt `LinkUpdate`, `user_id`.
  - Dla `delete_link`: `link_id`, `user_id`.
  - Dla `get_link_statistics`: `link_id`, `user_id`.
- **Opcjonalne dane:**
  - W `LinkCreate`: `default_url`.
  - W `LinkUpdate`: `default_url`.

## 3. Wykorzystywane typy

- **Modele Pydantic (DTOs - Wejście):**
  - `schemas.link.LinkCreate`
  - `schemas.link.LinkUpdate`
- **Modele Pydantic (DTOs - Wyjście):**
  - `schemas.link.LinkResponse`
  - `schemas.link.PaginatedLinkResponse`
  - `schemas.stats.LinkStatsResponse` (zawiera `schemas.stats.TargetClickStat`)
- **Typy Podstawowe:**
  - `uuid.UUID`
  - `int` (dla paginacji)
- **Klient Supabase:**
  - `supabase_py_async.AsyncClient` (lub `supabase.Client` dla sync) - **ważne:** ten serwis używa klienta inicjalizowanego w kontekście żądania użytkownika (z JWT), aby RLS działał poprawnie. _Wyjątek: Metoda statystyk może potrzebować dostępu do reguł, co może wymagać klienta service_role lub specyficznej polityki RLS, ale dla prostoty zakładamy, że RLS na rules też działa poprawnie w kontekście usera._
- **Wyjątki Supabase/DB:**
  - `gotrue.errors.AuthApiError` (jeśli używamy klienta z JWT)
  - `postgrest.exceptions.APIError` (lub odpowiednik dla `supabase-py v2+`)
  - Błąd naruszenia unikalności (np. kod `23505`)
- **Niestandardowe Wyjątki Aplikacyjne (`services.custom_exceptions`):**
  - `ServiceException`
  - `AliasConflictException(ServiceException)`
  - `DatabaseException(ServiceException)`
  - `NotFoundException(ServiceException)`
  - `ValidationException(ServiceException)` (opcjonalnie dla błędów logiki biznesowej)

## 4. Szczegóły działania serwisu

- **`create_link(link_data, user_id)`:** Wstawia nowy rekord do `routr_links`, używając danych wejściowych i `user_id`. Polega na RLS `WITH CHECK` i ograniczeniu `UNIQUE` bazy danych dla walidacji. Zwraca utworzony obiekt. Obsługuje błąd konfliktu aliasu.
- **`get_links_paginated(user_id, page, page_size)`:** Pobiera listę linków dla `user_id` z uwzględnieniem paginacji (`range` i `count='exact'`). Polega na RLS `USING`. Zwraca obiekt `PaginatedLinkResponse`.
- **`get_link_by_id(link_id, user_id)`:** Pobiera pojedynczy link po `id`. Polega na RLS `USING` do sprawdzenia własności. Zgłasza `NotFoundException`, jeśli link nie istnieje lub nie należy do użytkownika. Zwraca obiekt `LinkResponse`.
- **`update_link(link_id, update_data, user_id)`:**
  1.  Najpierw pobiera link (`get_link_by_id` lub podobne zapytanie `select`) w celu weryfikacji istnienia i własności (przez RLS `USING`). Jeśli nie znaleziono, zgłasza `NotFoundException`.
  2.  Przygotowuje słownik tylko z polami obecnymi w `update_data`.
  3.  Wykonuje `update` na `routr_links` z filtrem `id=link_id`. RLS `USING` dodatkowo zabezpiecza.
  4.  Pobiera i zwraca zaktualizowany obiekt `LinkResponse`.
- **`delete_link(link_id, user_id)`:** Wykonuje `delete` na `routr_links` z filtrem `id=link_id`. Polega na RLS `USING` do autoryzacji. Sprawdza liczbę usuniętych wierszy; jeśli 0, zgłasza `NotFoundException`. Nic nie zwraca w przypadku sukcesu.
- **`get_link_statistics(link_id, user_id)`:**
  1.  Pobiera podstawowe dane linku (`id`, `alias`, `total_clicks`) z `routr_links`, weryfikując własność przez RLS `USING`. Jeśli nie znaleziono, zgłasza `NotFoundException`.
  2.  Pobiera wszystkie powiązane reguły (`id`, `target_type`, `target_value`, `current_clicks`) z `routing_rules` dla danego `link_id`, sortując po `priority`. RLS `USING` na `routing_rules` (sprawdzający własność `link_id`) również się zastosuje.
  3.  Przetwarza dane reguł, tworząc `target_value_preview` dla każdego celu.
  4.  Konstruuje i zwraca obiekt `LinkStatsResponse`.

## 5. Przepływ danych

1.  **Handler Endpointu API** otrzymuje żądanie HTTP, waliduje parametry ścieżki/zapytania i ciało żądania (używając modeli Pydantic z `src/schemas/`). Uwierzytelnia użytkownika i uzyskuje `user_id` (przez zależność `deps.get_current_user_id`).
2.  Handler wywołuje odpowiednią metodę w instancji **`LinkService`**, przekazując `user_id` i przetworzone dane wejściowe (np. `link_id`, obiekt DTO).
3.  **Metoda `LinkService`** wykonuje logikę biznesową.
4.  Do interakcji z bazą danych, metoda serwisu używa wstrzykniętej instancji **klienta `supabase-py`** (z kontekstem JWT użytkownika).
5.  Klient `supabase-py` wysyła zapytania SQL (opakowane w żądania HTTP do PostgREST API Supabase) do **bazy danych PostgreSQL**.
6.  **Baza danych PostgreSQL** wykonuje zapytanie, stosując odpowiednie **polityki RLS** w oparciu o `user_id` przekazane w kontekście zapytania przez klienta Supabase (który uzyskał je z JWT). Baza danych również wymusza ograniczenia (`UNIQUE`, `CHECK`, `FK`).
7.  Baza danych zwraca wynik (dane lub błąd) do klienta `supabase-py`.
8.  Klient `supabase-py` zwraca dane lub zgłasza wyjątek (np. `APIError`) do metody `LinkService`.
9.  **Metoda `LinkService`** obsługuje odpowiedź/błąd:
    - W przypadku sukcesu: mapuje dane DB na odpowiedni model Pydantic DTO (`LinkResponse`, `PaginatedLinkResponse`, `LinkStatsResponse`) i zwraca go.
    - W przypadku błędu DB: przechwytuje wyjątek klienta Supabase/DB, analizuje go (np. kod błędu `23505` dla `UNIQUE violation`) i zgłasza odpowiedni **niestandardowy wyjątek aplikacyjny** (`AliasConflictException`, `NotFoundException`, `DatabaseException`).
10. **Handler Endpointu API** przechwytuje niestandardowe wyjątki z serwisu i mapuje je na `HTTPException` z odpowiednim kodem statusu HTTP (`409`, `404`, `500`). W przypadku sukcesu serializuje zwrócony obiekt DTO do JSON i wysyła odpowiedź HTTP (`200 OK`, `201 Created`, `204 No Content`).

## 6. Względy bezpieczeństwa

- **Autoryzacja:** Kluczowym mechanizmem jest poleganie na RLS w bazie danych. Każda metoda serwisu przyjmuje `user_id` i zakłada, że operacje DB wykonywane przez klienta Supabase będą automatycznie filtrowane/sprawdzane przez polityki RLS (`USING (auth.uid() = user_id)` lub `WITH CHECK (auth.uid() = user_id)`).
- **Weryfikacja Własności:** Dla operacji `update` i `delete`, zaleca się dodatkową weryfikację w serwisie (poprzez próbę odczytu zasobu przed modyfikacją/usunięciem), aby zapewnić bardziej precyzyjną obsługę błędów (np. rozróżnienie między "nie znaleziono" a "brak uprawnień", chociaż oba skutkują 404 dla klienta).
- **Walidacja Wejścia:** Serwis polega na modelach Pydantic (przekazywanych z warstwy API) do walidacji formatu i typów danych wejściowych. Dodatkowe walidacje logiki biznesowej (jeśli potrzebne) powinny być implementowane w serwisie.
- **Kontekst Klienta Supabase:** Należy upewnić się, że do metod `LinkService` wstrzykiwany jest klient Supabase działający w kontekście uwierzytelnionego użytkownika (z jego JWT), a _nie_ klient z kluczem `service_role`.

## 7. Obsługa błędów

Serwis powinien używać niestandardowych wyjątków dziedziczących po `ServiceException` do sygnalizowania konkretnych problemów biznesowych lub technicznych:

- **`create_link`:**
  - Błąd `UNIQUE constraint` na `alias` -> Zgłoś `AliasConflictException`. Handler API zwróci `409 Conflict`.
  - Inne błędy DB -> Zgłoś `DatabaseException`. Handler API zwróci `500 Internal Server Error`.
- **`get_links_paginated`:**
  - Błędy DB -> Zgłoś `DatabaseException`. Handler API zwróci `500 Internal Server Error`.
- **`get_link_by_id`:**
  - Link nie istnieje lub RLS odfiltrował -> Zapytanie zwróci 0 wierszy -> Zgłoś `NotFoundException`. Handler API zwróci `404 Not Found`.
  - Błędy DB -> Zgłoś `DatabaseException`. Handler API zwróci `500 Internal Server Error`.
- **`update_link`:**
  - Wstępne sprawdzenie własności nie powiodło się -> Zgłoś `NotFoundException`. Handler API zwróci `404 Not Found`.
  - Błędy DB podczas `update` -> Zgłoś `DatabaseException`. Handler API zwróci `500 Internal Server Error`.
- **`delete_link`:**
  - `DELETE` zwrócił `count=0` (nie znaleziono lub brak uprawnień RLS) -> Zgłoś `NotFoundException`. Handler API zwróci `404 Not Found`.
  - Błędy DB -> Zgłoś `DatabaseException`. Handler API zwróci `500 Internal Server Error`.
- **`get_link_statistics`:**
  - Wstępne sprawdzenie własności linku nie powiodło się -> Zgłoś `NotFoundException`. Handler API zwróci `404 Not Found`.
  - Błędy DB podczas pobierania linku lub reguł -> Zgłoś `DatabaseException`. Handler API zwróci `500 Internal Server Error`.

Wszystkie błędy `DatabaseException` lub inne nieoczekiwane wyjątki powinny być logowane w serwisie lub wyżej z odpowiednimi szczegółami.

## 8. Rozważania dotyczące wydajności

- **Zapytania DB:** Większość operacji (CRUD dla pojedynczego linku) opiera się na kluczu głównym (`id`) lub indeksowanym `alias`, co jest wydajne.
- **Paginacja:** `get_links_paginated` używa `LIMIT`/`OFFSET`. Może stać się mniej wydajne dla bardzo dużych numerów stron (problem "deep pagination"), ale jest akceptowalne dla MVP. Indeks na `user_id` jest kluczowy.
- **Statystyki:** `get_link_statistics` wykonuje dwa zapytania: jedno na `routr_links` (PK + RLS) i jedno na `routing_rules` (FK + RLS + sortowanie). Oba powinny być wydajne dzięki indeksom (`PK`, `FK`, `idx_routing_rules_link_id_priority`). Przetwarzanie wyników w Pythonie jest zazwyczaj szybkie dla rozsądnej liczby reguł.
- **RLS:** Proste polityki RLS oparte na `auth.uid() = user_id` mają zazwyczaj niewielki narzut wydajnościowy, jeśli kolumna `user_id` jest zaindeksowana.

## 9. Etapy wdrożenia

1.  **Utworzenie Pliku Serwisu:** Stwórz plik `src/services/link_service.py`.
2.  **Zdefiniowanie Klasy `LinkService`:** Dodaj `__init__(self, supabase: AsyncClient)`.
3.  **Implementacja `create_link`:** Dodaj metodę, logikę `insert`, obsługę błędu `UNIQUE` (`AliasConflictException`) i innych błędów DB (`DatabaseException`). Zwróć `LinkResponse`.
4.  **Implementacja `get_link_by_id`:** Dodaj metodę, logikę `select` z filtrem `id`, użyj `.maybe_single()`, obsłuż brak wyniku (`NotFoundException`) i błędy DB (`DatabaseException`). Zwróć `LinkResponse`.
5.  **Implementacja `get_links_paginated`:** Dodaj metodę, logikę `select` z `range()`, `order()`, `count='exact'`, obsługę błędów DB (`DatabaseException`). Skonstruuj i zwróć `PaginatedLinkResponse`.
6.  **Implementacja `update_link`:** Dodaj metodę. Zaimplementuj krok weryfikacji własności (np. wywołując `get_link_by_id` lub przez osobne zapytanie). Przygotuj dane do update'u (`exclude_unset=True`). Wykonaj `update` z filtrem `id`. Obsłuż błędy DB. Pobierz i zwróć zaktualizowany `LinkResponse`.
7.  **Implementacja `delete_link`:** Dodaj metodę. Wykonaj `delete` z filtrem `id`. Sprawdź `count` wyniku. Zgłoś `NotFoundException` jeśli count=0. Obsłuż błędy DB.
8.  **Implementacja `get_link_statistics`:** Dodaj metodę. Zaimplementuj dwuetapowe pobieranie danych (link, potem reguły). Sprawdź własność linku. Przetwórz wyniki reguł (generowanie `target_value_preview`). Skonstruuj i zwróć `LinkStatsResponse`. Obsłuż błędy (`NotFoundException`, `DatabaseException`).
9.  **Dodanie Logowania:** Wzbogać metody o logowanie kluczowych operacji i błędów.
10. **Testy Jednostkowe:** Stwórz `tests/services/test_link_service.py`. Napisz testy dla każdej metody publicznej, mockując klienta Supabase i symulując różne scenariusze (sukces, błędy DB, konflikty, nieznalezione zasoby). Sprawdź poprawność zwracanych danych i zgłaszanych wyjątków.
