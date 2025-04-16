# Service Implementation Plan: RedirectionService

## 1. Przegląd serwisu

`RedirectionService` implementuje kluczową logikę publicznego punktu końcowego przekierowań `/{alias_path:path}`. Jego zadaniem jest przyjęcie aliasu linku, odnalezienie odpowiedniego linku i jego reguł w bazie danych, ewaluacja tych reguł w oparciu o priorytet i warunki (czas, liczba kliknięć), a następnie zwrócenie informacji o akcji, którą powinien podjąć handler API (przekierowanie URL, serwowanie HTML, przekierowanie domyślne lub globalne). Serwis jest również odpowiedzialny za atomowe inkrementowanie liczników kliknięć (`total_clicks` dla linku i `current_clicks` dla dopasowanej reguły). Ze względu na publiczny charakter endpointu i potrzebę odczytu dowolnych danych linków/reguł, ten serwis **musi** używać klienta Supabase skonfigurowanego z kluczem `service_role`, aby ominąć polityki RLS.

## 2. Szczegóły wejścia

- **Rodzaj danych:** Parametry prymitywne.
- **Wymagane dane:**
  - Dla `process_redirection`: `alias_path` (str) - alias z ścieżki URL.
- **Opcjonalne dane:** Brak.

## 3. Wykorzystywane typy

- **Typy Podstawowe:**
  - `str` (dla `alias_path`)
  - `uuid.UUID` (dla identyfikatorów pobieranych z DB)
- **Modele Pydantic (DTOs - Wewnętrzne/Wyjście):** Brak standardowych DTO, serwis zwraca krotkę lub dedykowany obiekt/enum.
- **Typy Pomocnicze:**
  - `enum.Enum` do zdefiniowania `RedirectionAction` (np. `REDIRECT_URL`, `SERVE_HTML`, `REDIRECT_DEFAULT`, `REDIRECT_GLOBAL_FALLBACK`).
  - `typing.Tuple[RedirectionAction, Optional[str]]` jako typ zwracany przez `process_redirection`.
- **Klient Supabase:**
  - `supabase_py_async.AsyncClient` (lub `supabase.Client`) - **ważne:** instancja skonfigurowana z **kluczem `service_role`**.
- **Wyjątki Supabase/DB:**
  - `postgrest.exceptions.APIError`
  - Potencjalne błędy związane z operacjami `UPDATE` (np. błędy blokad, chociaż mało prawdopodobne przy prostych inkrementacjach).
- **Niestandardowe Wyjątki Aplikacyjne (`services.custom_exceptions`):**
  - `ServiceException`
  - `LinkNotFoundException(NotFoundException)`: Gdy alias nie zostanie znaleziony w `routr_links`.
  - `DatabaseException(ServiceException)`: Dla ogólnych błędów DB podczas SELECT lub UPDATE.

## 4. Szczegóły działania serwisu

- **`process_redirection(alias_path)`:**
  1.  **Znajdź Link:** Wykonuje `select id, default_url` na `routr_links` filtrując `WHERE alias = alias_path` (używając klienta `service_role`). Jeśli nie znaleziono, zgłasza `LinkNotFoundException`. Zapamiętuje `link_id` i `default_url`.
  2.  **Inkrementuj Licznik Linku:** Wykonuje **atomowe** `UPDATE routr_links SET total_clicks = total_clicks + 1 WHERE id = link_id` (używając klienta `service_role`). Loguje ewentualne błędy, ale _nie przerywa_ przetwarzania (priorytetem jest przekierowanie).
  3.  **Pobierz Reguły:** Wykonuje `select id, priority, rule_type, target_type, target_value, start_time, end_time, max_clicks, current_clicks` na `routing_rules` filtrując `WHERE link_id = link_id` i sortując `ORDER BY priority ASC` (używając klienta `service_role`).
  4.  **Ewaluuj Reguły:** Iteruje przez pobrane reguły:
      - Sprawdza warunek zgodnie z `rule_type`:
        - 'time': `start_time <= now_utc <= end_time`
        - 'clicks': `current_clicks < max_clicks`
      - Jeśli warunek jest spełniony (`rule_matched = True`):
        - Zapamiętuje `matched_rule_id`, `target_type`, `target_value`.
        - Przerywa pętlę.
  5.  **Obsłuż Wynik Ewaluacji:**
      - Jeśli `rule_matched == True`:
        - **Inkrementuj Licznik Reguły:** Wykonuje **atomowe** `UPDATE routing_rules SET current_clicks = current_clicks + 1 WHERE id = matched_rule_id` (używając klienta `service_role`). Loguje ewentualne błędy.
        - Jeśli `target_type == 'url'`, zwraca `(RedirectionAction.REDIRECT_URL, target_value)`.
        - Jeśli `target_type == 'html'`, zwraca `(RedirectionAction.SERVE_HTML, target_value)`.
      - Jeśli `rule_matched == False`:
        - Jeśli `default_url` (pobrany w kroku 1) nie jest `None`, zwraca `(RedirectionAction.REDIRECT_DEFAULT, default_url)`.
        - W przeciwnym razie, zwraca `(RedirectionAction.REDIRECT_GLOBAL_FALLBACK, None)`.
  6.  W przypadku błędów DB podczas SELECT (krok 1 lub 3), zgłasza `DatabaseException`.

## 5. Przepływ danych

1.  **Endpoint API (`/{alias_path:path}`)** otrzymuje żądanie HTTP GET.
2.  Handler endpointu wywołuje metodę **`RedirectionService.process_redirection`**, przekazując `alias_path`.
3.  **Metoda `process_redirection`** używa wstrzykniętego klienta **`supabase-py` (z kluczem `service_role`)**.
4.  Serwis wykonuje zapytanie **`SELECT`** do `routr_links` w celu znalezienia `link_id` i `default_url`.
5.  Jeśli link znaleziono, serwis wykonuje atomowe zapytanie **`UPDATE`** na `routr_links` w celu inkrementacji `total_clicks`.
6.  Serwis wykonuje zapytanie **`SELECT`** do `routing_rules` w celu pobrania reguł dla `link_id`.
7.  Serwis **ewaluuje reguły** w pamięci aplikacji.
8.  Jeśli reguła zostanie dopasowana, serwis wykonuje atomowe zapytanie **`UPDATE`** na `routing_rules` w celu inkrementacji `current_clicks` dla tej reguły.
9.  Serwis zwraca krotkę `(RedirectionAction, Optional[str])` do handlera endpointu.
10. Handler endpointu konstruuje i zwraca odpowiednią odpowiedź HTTP (`RedirectResponse` lub `HTMLResponse`).

## 6. Względy bezpieczeństwa

- **Klucz `service_role`:** Ten serwis _musi_ używać klucza `service_role` Supabase. Klucz ten ma pełne uprawnienia do bazy danych i omija RLS. Należy go przechowywać i zarządzać nim w sposób wyjątkowo bezpieczny (np. jako sekret w środowisku produkcyjnym, niedostępny w kodzie źródłowym). Nadużycie tego klucza stanowi poważne zagrożenie.
- **Walidacja Wejścia:** Jedynym wejściem jest `alias_path`. Walidacja polega na sprawdzeniu jego istnienia w bazie. Bezpośrednie użycie `alias_path` w zapytaniach SQL jest bezpieczne, jeśli używane są parametryzowane zapytania (co zapewnia klient `supabase-py`).
- **XSS (Cross-Site Scripting):** Jeśli wynikiem jest `RedirectionAction.SERVE_HTML`, serwis zwraca surowy HTML pobrany z bazy. Odpowiedzialność za bezpieczeństwo tego HTML leży w procesie jego tworzenia/aktualizacji przez użytkownika (obsługiwanym przez `RuleService` i API zarządzania). Ten serwis nie wykonuje sanitizacji.
- **Open Redirect:** Podobnie jak przy XSS, bezpieczeństwo przed otwartymi przekierowaniami zależy od walidacji `target_value` typu 'url' podczas tworzenia/aktualizacji reguł.
- **DoS / Obciążenie Bazy Danych:** Wielokrotne wywołania dla tego samego lub różnych aliasów generują operacje `UPDATE` na licznikach. Należy zastosować rate limiting na poziomie infrastruktury lub aplikacji, aby chronić bazę danych przed nadmiernym obciążeniem zapisami.

## 7. Obsługa błędów

- **Alias nie istnieje:** `SELECT` na `routr_links` nie zwraca wiersza -> Zgłoś `LinkNotFoundException`. Handler API zwróci `404 Not Found`.
- **Błąd Bazy Danych (SELECT):** Problem podczas pobierania linku lub reguł -> Zgłoś `DatabaseException`. Handler API zwróci `500 Internal Server Error`.
- **Błąd Bazy Danych (UPDATE liczników):** Problem podczas inkrementacji `total_clicks` lub `current_clicks`. Serwis powinien **zalogować błąd**, ale _kontynuować_ przetwarzanie, jeśli to możliwe (przekierowanie jest ważniejsze niż 100% dokładność licznika w przypadku przejściowych błędów zapisu). Jeśli błąd uniemożliwia kontynuację, zgłosić `DatabaseException` -> Handler zwróci `500 Internal Server Error`.
- **Nieoczekiwane błędy w logice:** Wszelkie inne wyjątki -> Zgłosić `ServiceException` lub pozwolić na propagację -> Handler zwróci `500 Internal Server Error`.

Szczegółowe logowanie błędów po stronie serwera jest kluczowe dla diagnozowania problemów z przekierowaniami.

## 8. Rozważania dotyczące wydajności

- **Zapytania DB:** Dwa zapytania `SELECT` i potencjalnie dwa atomowe `UPDATE` per żądanie. `SELECT`y są szybkie dzięki indeksom (`idx_routr_links_alias`, `idx_routing_rules_link_id_priority`). `UPDATE`y na PK również są szybkie, ale generują obciążenie zapisu.
- **Ewaluacja Reguł:** Prosta logika warunkowa w Pythonie, bardzo szybka dla typów reguł MVP.
- **Współbieżność Liczników:** Atomowe operacje `UPDATE` (`counter = counter + 1`) są kluczowe, aby uniknąć race conditions, ale mogą prowadzić do rywalizacji o blokady wierszy przy bardzo wysokiej częstotliwości kliknięć tego samego linku/reguły. PostgreSQL dobrze sobie z tym radzi, ale jest to główny potencjalny punkt skalowania.
- **Strategie Optymalizacji (Post-MVP):**
  - **Cache'owanie:** Cache'owanie danych linków i reguł (np. w Redis lub pamięci aplikacji z TTL) dla często używanych aliasów może znacząco zredukować liczbę zapytań `SELECT`. Wymaga to jednak strategii unieważniania cache'a przy aktualizacji linku/reguł.
  - **Kolejkowanie Aktualizacji Liczników:** W przypadku ekstremalnego obciążenia, można rozważyć logowanie kliknięć do szybkiego systemu (np. Redis, kolejka wiadomości) i aktualizowanie liczników w bazie danych asynchronicznie przez osobny proces/zadanie w tle. To znacznie zwiększa złożoność.
  - **Rate Limiting:** Niezbędne do ochrony przed nadużyciami i kontrolowania obciążenia.

## 9. Etapy wdrożenia

1.  **Utworzenie Pliku Serwisu:** Stwórz plik `src/services/redirection_service.py`.
2.  **Zdefiniowanie Enum `RedirectionAction`:** Dodaj enum w `redirection_service.py` lub wspólnym module (np. `src/core/enums.py`).
3.  **Zdefiniowanie Wyjątku `LinkNotFoundException`:** Dodaj w `src/services/custom_exceptions.py`.
4.  **Implementacja Klasy `RedirectionService`:**
    - Dodaj `__init__(self, supabase_client: AsyncClient)`. Upewnij się, że wstrzykiwany jest klient z `service_role`.
5.  **Implementacja Metody `process_redirection`:**
    - Zaimplementuj logikę krok po kroku (punkty 4.1 - 4.6 z sekcji "Szczegóły działania serwisu").
    - Użyj `async`/`await` dla wywołań klienta Supabase.
    - Zastosuj atomowe operacje `UPDATE` dla liczników (sprawdź składnię w `supabase-py`, może wymagać wywołania funkcji RPC lub specyficznej konstrukcji update). Przykład: `await self.supabase_client.table('routr_links').update({'total_clicks': PostgrestQueryBuilder(f"total_clicks + 1")}).eq('id', link_id).execute()` - _Uwaga: Dokładna składnia dla atomowej inkrementacji może wymagać dostosowania lub funkcji DB_. Lub użyj `rpc`.
    - Zaimplementuj logikę ewaluacji reguł ('time', 'clicks'). Pamiętaj o UTC dla czasu.
    - Implementuj logikę obsługi wyniku (dopasowana reguła, default, global fallback).
    - Dodaj bloki `try...except` do obsługi `LinkNotFoundException` i ogólnych `DatabaseException` / `Exception`, dodając logowanie.
    - Zwróć krotkę `(RedirectionAction, Optional[str])`.
6.  **Testy Jednostkowe:**
    - Stwórz `tests/services/test_redirection_service.py`.
    - Napisz testy jednostkowe dla `process_redirection`, mockując klienta Supabase (`service_role`).
    - Testuj różne scenariusze:
      - Znaleziono alias, pasuje reguła 'time' (w czasie).
      - Znaleziono alias, pasuje reguła 'clicks' (poniżej limitu).
      - Znaleziono alias, pasuje reguła 'time', ale poza czasem -> pasuje kolejna reguła 'clicks'.
      - Znaleziono alias, reguła 'clicks' osiągnęła limit -> pasuje kolejna reguła.
      - Znaleziono alias, żadna reguła nie pasuje, jest `default_url`.
      - Znaleziono alias, żadna reguła nie pasuje, brak `default_url`.
      - Alias nie istnieje.
    - Weryfikuj zwracaną akcję i wartość.
    - Weryfikuj (przez mockowanie) czy odpowiednie metody `update` na kliencie Supabase (dla liczników) są wywoływane z poprawnymi argumentami.
    - Testuj zgłaszanie wyjątków `LinkNotFoundException` i `DatabaseException` przy symulowanych błędach klienta Supabase.
