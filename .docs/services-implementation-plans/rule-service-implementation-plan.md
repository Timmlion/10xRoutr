# Service Implementation Plan: RuleService

## 1. Przegląd serwisu

`RuleService` zarządza logiką biznesową dla zasobów `routing_rules`. Odpowiada za tworzenie, odczytywanie (pojedyncze i listy), aktualizowanie oraz usuwanie reguł powiązanych z konkretnym linkiem (`routr_links`). Kluczowym aspektem jest zapewnienie, że wszystkie operacje są wykonywane w kontekście uwierzytelnionego użytkownika i tylko na regułach należących do linków tego użytkownika. W tym celu serwis współpracuje z `LinkService` (do weryfikacji własności linku) lub bezpośrednio sprawdza własność linku przed modyfikacją reguł i polega na RLS w bazie danych.

## 2. Szczegóły wejścia

- **Rodzaj danych:** Obiekty Pydantic DTO dla tworzenia (`RuleCreate`) i aktualizacji (`RuleUpdate`), identyfikatory UUID dla użytkownika (`user_id`), linku (`link_id`) i reguły (`rule_id`).
- **Wymagane dane:**
  - Dla `add_rule_to_link`: `link_id`, obiekt `RuleCreate`, `user_id`.
  - Dla `get_rules_for_link`: `link_id`, `user_id`.
  - Dla `get_rule_details`: `link_id`, `rule_id`, `user_id`.
  - Dla `update_rule`: `link_id`, `rule_id`, obiekt `RuleUpdate`, `user_id`.
  - Dla `delete_rule`: `link_id`, `rule_id`, `user_id`.
- **Opcjonalne dane:**
  - W `RuleCreate`: `start_time`, `end_time`, `max_clicks` (warunkowo wymagane na podstawie `rule_type`).
  - W `RuleUpdate`: Wszystkie pola są opcjonalne (`priority`, `rule_type`, `target_type`, `target_value`, `start_time`, `end_time`, `max_clicks`).

## 3. Wykorzystywane typy

- **Modele Pydantic (DTOs - Wejście):**
  - `schemas.rule.RuleCreate`
  - `schemas.rule.RuleUpdate`
- **Modele Pydantic (DTOs - Wyjście):**
  - `schemas.rule.RuleResponse`
  - `List[schemas.rule.RuleResponse]`
- **Typy Podstawowe:**
  - `uuid.UUID`
- **Klient Supabase:**
  - `supabase_py_async.AsyncClient` (lub `supabase.Client`) - w kontekście JWT użytkownika.
- **Wyjątki Supabase/DB:**
  - `gotrue.errors.AuthApiError`
  - `postgrest.exceptions.APIError`
  - Błąd naruszenia unikalności (kod `23505` dla `(link_id, priority)`)
- **Niestandardowe Wyjątki Aplikacyjne (`services.custom_exceptions`):**
  - `ServiceException`
  - `ParentLinkNotFoundException(NotFoundException)`: Specyficzny wyjątek, gdy link nadrzędny nie istnieje lub nie należy do użytkownika.
  - `NotFoundException(ServiceException)`: Dla nieznalezionej reguły.
  - `PriorityConflictException(ServiceException)`: Dla konfliktu priorytetów.
  - `ValidationException(ServiceException)`: Dla błędów walidacji logiki biznesowej (np. niespójność danych w `update_rule`).
  - `DatabaseException(ServiceException)`: Dla ogólnych błędów DB.
- **Inne Serwisy (Opcjonalnie):**
  - Potencjalnie `LinkService` do weryfikacji własności linku, jeśli ta logika nie jest powielana w `RuleService`.

## 4. Szczegóły działania serwisu

- **Weryfikacja Własności Linku Nadrzędnego:** _Każda_ metoda modyfikująca lub odczytująca reguły dla konkretnego `link_id` _musi_ najpierw upewnić się, że link o podanym `link_id` istnieje i należy do przekazanego `user_id`. Najprościej jest wykonać szybkie zapytanie `select id from routr_links where id = link_id` używając klienta Supabase z kontekstem użytkownika (RLS sprawdzi własność). Jeśli zapytanie nie zwróci rekordu, metoda powinna zgłosić `ParentLinkNotFoundException`.
- **`add_rule_to_link(link_id, rule_data, user_id)`:**
  1.  Weryfikuje własność `link_id`.
  2.  Przygotowuje dane do wstawienia (łącząc `link_id` i dane z `rule_data`).
  3.  Wykonuje `insert` do `routing_rules`.
  4.  Obsługuje błąd konfliktu priorytetu (`PriorityConflictException`) i inne błędy DB (`DatabaseException`).
  5.  Zwraca utworzony obiekt `RuleResponse`.
- **`get_rules_for_link(link_id, user_id)`:**
  1.  Weryfikuje własność `link_id`.
  2.  Wykonuje `select` na `routing_rules` filtrując po `link_id` i sortując po `priority`. RLS dodatkowo zabezpiecza.
  3.  Zwraca listę obiektów `RuleResponse`.
- **`get_rule_details(link_id, rule_id, user_id)`:**
  1.  Wykonuje `select` na `routing_rules` filtrując po `id = rule_id` ORAZ `link_id = link_id`. RLS weryfikuje własność `link_id`.
  2.  Jeśli nie znaleziono, zgłasza `NotFoundException`.
  3.  Zwraca znaleziony obiekt `RuleResponse`.
- **`update_rule(link_id, rule_id, update_data, user_id)`:**
  1.  Pobiera bieżący stan reguły (jak w `get_rule_details`), co jednocześnie weryfikuje istnienie i własność. Jeśli nie znaleziono, zgłasza `NotFoundException`.
  2.  Łączy bieżące dane z `update_data`, tworząc `final_state`.
  3.  Waliduje spójność danych w `final_state` (wymagane pola dla typu, poprawność URL, `end_time` > `start_time`, etc.). Jeśli błąd, zgłasza `ValidationException`.
  4.  Przygotowuje `db_update_payload` tylko ze zmienionymi i istotnymi polami (zerując niepotrzebne).
  5.  Jeśli payload nie jest pusty, wykonuje `update` na `routing_rules` filtrując po `id = rule_id`. RLS dodatkowo zabezpiecza.
  6.  Obsługuje błąd konfliktu priorytetu (`PriorityConflictException`) i inne błędy DB (`DatabaseException`).
  7.  Pobiera (jeśli `update` nie zwrócił) i zwraca zaktualizowany obiekt `RuleResponse`.
- **`delete_rule(link_id, rule_id, user_id)`:**
  1.  Wykonuje `delete` na `routing_rules` filtrując po `id = rule_id` ORAZ `link_id = link_id`. RLS zabezpiecza operację.
  2.  Sprawdza liczbę usuniętych wierszy. Jeśli 0, zgłasza `NotFoundException`.
  3.  Nic nie zwraca w przypadku sukcesu.

## 5. Przepływ danych

1.  **Handler Endpointu API** (`/links/{link_id}/rules/...`) otrzymuje żądanie, waliduje parametry/ciało, uwierzytelnia użytkownika (`user_id`).
2.  Handler wywołuje odpowiednią metodę **`RuleService`**, przekazując `link_id`, `rule_id` (jeśli dotyczy), `user_id` i dane DTO.
3.  **Metoda `RuleService`** najpierw (dla większości operacji) wykonuje zapytanie **`SELECT`** do `routr_links` (używając klienta Supabase z **kontekstem JWT użytkownika**) w celu weryfikacji istnienia i własności `link_id`. RLS w bazie danych dokonuje faktycznej autoryzacji.
4.  Jeśli weryfikacja własności linku się powiedzie, metoda serwisu wykonuje główną operację (np. `INSERT`, `SELECT`, `UPDATE`, `DELETE`) na tabeli **`routing_rules`** (ponownie używając klienta Supabase z **kontekstem JWT użytkownika**). RLS na `routing_rules` zapewnia dodatkową warstwę bezpieczeństwa.
5.  Baza danych **PostgreSQL** wykonuje operację, stosując polityki RLS i ograniczenia (`UNIQUE`, `CHECK`).
6.  Wynik lub błąd jest zwracany przez **klienta Supabase** do `RuleService`.
7.  **`RuleService`** przetwarza wynik/błąd, mapuje dane na DTO lub zgłasza odpowiedni **niestandardowy wyjątek aplikacyjny**.
8.  **Handler Endpointu API** przechwytuje wyjątek i mapuje go na `HTTPException`. W przypadku sukcesu zwraca zserializowaną odpowiedź DTO.

## 6. Względy bezpieczeństwa

- **Autoryzacja:** Kluczowe jest konsekwentne sprawdzanie własności linku nadrzędnego (`link_id`) we _wszystkich_ metodach serwisu przed wykonaniem operacji na regułach. Poleganie na RLS jest podstawą, ale jawne sprawdzenie w serwisie poprawia obsługę błędów (zwracanie poprawnego 404 zamiast potencjalnego błędu RLS). Wszystkie operacje DB w tym serwisie muszą używać klienta Supabase z kontekstem JWT użytkownika.
- **Walidacja Wejścia:** Walidacja Pydantic w warstwie API + dodatkowa walidacja spójności w metodzie `update_rule` w serwisie + ograniczenia `CHECK` i `UNIQUE` w bazie danych tworzą wielowarstwową ochronę przed niepoprawnymi danymi.
- **Bezpieczeństwo HTML:** Należy pamiętać o ryzyku XSS związanym z przechowywaniem i potencjalnym wyświetlaniem `target_value` typu 'html'. Chociaż serwis bezpośrednio nie odpowiada za sanitizację (jest to bardziej kwestia endpointu `create/update`), należy to uwzględnić w kontekście bezpieczeństwa danych przechowywanych przez serwis.

## 7. Obsługa błędów

Serwis mapuje błędy na niestandardowe wyjątki:

- **Brak linku nadrzędnego lub brak uprawnień:** -> `ParentLinkNotFoundException`. Handler zwróci `404 Not Found`.
- **Brak reguły (dla get/update/delete):** -> `NotFoundException`. Handler zwróci `404 Not Found`.
- **Konflikt priorytetu (dla create/update):** -> `PriorityConflictException`. Handler zwróci `409 Conflict`.
- **Niespójne dane w update:** -> `ValidationException` lub `BadRequestException`. Handler zwróci `400 Bad Request`.
- **Inne błędy DB (np. naruszenie CHECK):** -> `DatabaseException`. Handler zwróci `500 Internal Server Error` (lub potencjalnie 400, jeśli błąd wskazuje na problem z danymi wejściowymi).
- **Błędy komunikacji z Supabase:** -> `DatabaseException` lub `ServiceException`. Handler zwróci `500 Internal Server Error`.

Logowanie powinno być stosowane przy przechwytywaniu błędów DB/Supabase przed zgłoszeniem niestandardowego wyjątku.

## 8. Rozważania dotyczące wydajności

- **Weryfikacja Własności Linku:** Dodatkowe zapytanie `SELECT` do `routr_links` w każdej metodzie wprowadza niewielki narzut, ale jest kluczowe dla bezpieczeństwa i poprawnej obsługi błędów. Jest to szybkie zapytanie oparte na PK i indeksie FK `user_id`.
- **Zapytania CRUD na Regułach:** Operacje na `routing_rules` (filtrowanie po `link_id` i/lub `id`, sortowanie po `priority`) są dobrze wspierane przez indeksy (FK, PK, `idx_routing_rules_link_id_priority`).
- **Konflikt Priorytetu:** Sprawdzanie ograniczenia `UNIQUE(link_id, priority)` podczas `INSERT`/`UPDATE` jest wydajne dzięki indeksowi.
- **Liczba Reguł:** Podobnie jak w `LinkService`, wydajność `get_rules_for_link` może się degradować, jeśli link ma ekstremalnie dużą liczbę reguł, ale jest to problem poza zakresem MVP.

## 9. Etapy wdrożenia

1.  **Utworzenie Pliku Serwisu:** Stwórz plik `src/services/rule_service.py`.
2.  **Zdefiniowanie Klasy `RuleService`:** Dodaj `__init__(self, supabase: AsyncClient)`. Rozważ dodanie zależności do `LinkService`, jeśli logika weryfikacji własności linku ma być współdzielona, lub zaimplementuj ją bezpośrednio w `RuleService`.
3.  **Implementacja Metody Weryfikacji Własności Linku:** Stwórz prywatną metodę pomocniczą `async def _verify_link_ownership(self, link_id: UUID, user_id: UUID)` która wykonuje `select id from routr_links...` i zgłasza `ParentLinkNotFoundException` w razie niepowodzenia.
4.  **Implementacja `add_rule_to_link`:**
    - Wywołaj `_verify_link_ownership`.
    - Przygotuj dane i wykonaj `insert` do `routing_rules`.
    - Obsłuż błąd unikalności priorytetu (`PriorityConflictException`) i inne błędy DB (`DatabaseException`).
    - Zwróć `RuleResponse`.
5.  **Implementacja `get_rules_for_link`:**
    - Wywołaj `_verify_link_ownership`.
    - Wykonaj `select` na `routing_rules` z `order by priority`.
    - Obsłuż błędy DB.
    - Zwróć `List[RuleResponse]`.
6.  **Implementacja `get_rule_details`:**
    - Wykonaj `select` na `routing_rules` z filtrem `id` i `link_id`. RLS zajmie się resztą.
    - Użyj `maybe_single()`. Jeśli `None`, zgłoś `NotFoundException`.
    - Obsłuż błędy DB.
    - Zwróć `RuleResponse`.
7.  **Implementacja `update_rule`:**
    - Wywołaj `get_rule_details`, aby pobrać bieżący stan i zweryfikować własność (obsłuży `NotFoundException`).
    - Połącz dane, zweryfikuj spójność (zgłoś `ValidationException` w razie problemu).
    - Przygotuj payload `update`.
    - Jeśli payload niepusty, wykonaj `update`. Obsłuż błąd konfliktu priorytetu (`PriorityConflictException`) i inne błędy DB.
    - Pobierz (jeśli trzeba) i zwróć zaktualizowany `RuleResponse`.
8.  **Implementacja `delete_rule`:**
    - Wykonaj `delete` na `routing_rules` z filtrem `id` i `link_id`. RLS zabezpieczy.
    - Sprawdź `count`. Jeśli 0, zgłoś `NotFoundException`.
    - Obsłuż błędy DB.
9.  **Dodanie Logowania:** Dodaj logowanie dla błędów i kluczowych operacji.
10. **Testy Jednostkowe:** Stwórz `tests/services/test_rule_service.py`. Napisz testy dla każdej metody, mockując klienta Supabase i (jeśli używane) `LinkService`. Testuj scenariusze sukcesu, różne przypadki błędów (nieznaleziony link, nieznaleziona reguła, konflikt priorytetu, błędy DB) i weryfikuj zwracane dane lub zgłaszane wyjątki.
