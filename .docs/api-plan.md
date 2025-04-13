# Plan API REST - routr (MVP)

Ten dokument przedstawia projekt API RESTful dla interfejsu zarządzania aplikacji _routr_ (MVP), oparty na dostarczonym Dokumencie Wymagań Produktu (PRD), schemacie bazy danych i stosie technologicznym.

## 1. Zasoby

- **Linki (`/links`):** Reprezentują zarządzane przez użytkownika linki routr. Odpowiadają tabeli bazy danych `routr_links`.
- **Reguły (`/links/{id_linku}/rules`):** Reprezentują reguły routingu powiązane z konkretnym linkiem. Odpowiadają tabeli bazy danych `routing_rules`.
- **Statystyki (`/links/{id_linku}/stats`):** Reprezentują statystyki kliknięć dla konkretnego linku. Dane pochodzą z tabel `routr_links` i `routing_rules`.
- **Uwierzytelnianie (`/auth`):** Obsługuje logowanie użytkownika i potencjalnie rejestrację (integruje się z Supabase Auth).

_(Uwaga: Kluczowa publiczna funkcjonalność przekierowania dostępna pod `routr.app/{alias}` jest obsługiwana przez oddzielny, nie-RESTful endpoint w aplikacji FastAPI i nie jest szczegółowo opisana w tym planie API zarządzania)._

## 2. Punkty końcowe

---

### 2.1. Zasób Linki (`/links`)

#### **Utwórz Link**

- **Metoda:** `POST`
- **Ścieżka:** `/links`
- **Opis:** Tworzy nowy link routr dla uwierzytelnionego użytkownika.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Ciało żądania:**
  ```json
  {
    "alias": "ciąg znaków (wymagany, unikalny, 3-64 znaki, ^[a-z0-9-]+$)",
    "default_url": "ciąg znaków (opcjonalny, poprawny format URL)"
  }
  ```
- **Ciało odpowiedzi (Sukces):**
  ```json
  {
    "id": "uuid",
    "user_id": "uuid",
    "alias": "ciąg znaków",
    "default_url": "ciąg znaków | null",
    "total_clicks": 0,
    "created_at": "znacznik_czasu_iso_z_strefą",
    "updated_at": "znacznik_czasu_iso_z_strefą"
  }
  ```
- **Kod sukcesu:** `201 Created`
- **Kody błędów:**
  - `400 Bad Request`: Nieprawidłowy format danych wejściowych (np. błąd walidacji aliasu).
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `409 Conflict`: Alias już istnieje (naruszenie ograniczenia unikalności bazy danych).
  - `422 Unprocessable Entity`: Błąd walidacji z modelu Pydantic.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

#### **Pobierz Listę Linków**

- **Metoda:** `GET`
- **Ścieżka:** `/links`
- **Opis:** Pobiera listę linków routr należących do uwierzytelnionego użytkownika. Obsługuje paginację.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry zapytania:**
  - `page`: `liczba całkowita` (opcjonalny, domyślnie: 1) - Numer strony paginacji.
  - `page_size`: `liczba całkowita` (opcjonalny, domyślnie: 20) - Liczba elementów na stronie.
- **Ciało odpowiedzi (Sukces):**
  ```json
  {
    "items": [
      {
        "id": "uuid",
        "user_id": "uuid",
        "alias": "ciąg znaków",
        "default_url": "ciąg znaków | null",
        "total_clicks": "liczba całkowita",
        "created_at": "znacznik_czasu_iso_z_strefą",
        "updated_at": "znacznik_czasu_iso_z_strefą"
      }
    ],
    "total": "liczba całkowita",
    "page": "liczba całkowita",
    "page_size": "liczba całkowita"
  }
  ```
  _(Uwaga: Dla interakcji z HTMX, ten endpoint może alternatywnie zwracać fragment HTML reprezentujący listę)._
- **Kod sukcesu:** `200 OK`
- **Kody błędów:**
  - `400 Bad Request`: Nieprawidłowe parametry paginacji.
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

#### **Pobierz Link**

- **Metoda:** `GET`
- **Ścieżka:** `/links/{id_linku}`
- **Opis:** Pobiera szczegóły konkretnego linku routr należącego do uwierzytelnionego użytkownika.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku do pobrania.
- **Ciało odpowiedzi (Sukces):**
  ```json
  {
    "id": "uuid",
    "user_id": "uuid",
    "alias": "ciąg znaków",
    "default_url": "ciąg znaków | null",
    "total_clicks": "liczba całkowita",
    "created_at": "znacznik_czasu_iso_z_strefą",
    "updated_at": "znacznik_czasu_iso_z_strefą"
  }
  ```
- **Kod sukcesu:** `200 OK`
- **Kody błędów:**
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem tego linku.
  - `404 Not Found`: Link o podanym ID nie został znaleziony.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

#### **Zaktualizuj Link**

- **Metoda:** `PATCH`
- **Ścieżka:** `/links/{id_linku}`
- **Opis:** Aktualizuje konfigurowalne szczegóły (obecnie tylko `default_url`) konkretnego linku routr należącego do uwierzytelnionego użytkownika. Alias nie może być zmieniony.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku do aktualizacji.
- **Ciało żądania:**
  ```json
  {
    "default_url": "ciąg znaków | null (opcjonalny, poprawny format URL lub null)"
    // Alias jest celowo pominięty - nie można go aktualizować
  }
  ```
- **Ciało odpowiedzi (Sukces):**
  ```json
  {
    "id": "uuid",
    "user_id": "uuid",
    "alias": "ciąg znaków",
    "default_url": "ciąg znaków | null",
    "total_clicks": "liczba całkowita",
    "created_at": "znacznik_czasu_iso_z_strefą",
    "updated_at": "znacznik_czasu_iso_z_strefą" // Powinien odzwierciedlać czas aktualizacji
  }
  ```
- **Kod sukcesu:** `200 OK`
- **Kody błędów:**
  - `400 Bad Request`: Nieprawidłowy format danych wejściowych (np. błąd walidacji URL).
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem tego linku.
  - `404 Not Found`: Link o podanym ID nie został znaleziony.
  - `422 Unprocessable Entity`: Błąd walidacji.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

#### **Usuń Link**

- **Metoda:** `DELETE`
- **Ścieżka:** `/links/{id_linku}`
- **Opis:** Usuwa konkretny link routr i wszystkie powiązane z nim reguły należące do uwierzytelnionego użytkownika.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku do usunięcia.
- **Ciało odpowiedzi (Sukces):** Brak (Puste Ciało).
- **Kod sukcesu:** `204 No Content`
- **Kody błędów:**
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem tego linku.
  - `404 Not Found`: Link o podanym ID nie został znaleziony.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

---

### 2.2. Zasób Reguły (`/links/{id_linku}/rules`)

#### **Utwórz Regułę**

- **Metoda:** `POST`
- **Ścieżka:** `/links/{id_linku}/rules`
- **Opis:** Dodaje nową regułę routingu do konkretnego linku należącego do uwierzytelnionego użytkownika.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku, do którego ma być dodana reguła.
- **Ciało żądania:**
  ```json
  {
    "priority": "liczba całkowita (wymagana, dodatnia, unikalna w obrębie linku)",
    "rule_type": "ciąg znaków (wymagany, 'time' lub 'clicks')",
    "target_type": "ciąg znaków (wymagany, 'url' lub 'html')",
    "target_value": "ciąg znaków (wymagany, poprawny URL jeśli target_type='url', kod HTML jeśli target_type='html')",
    "start_time": "znacznik_czasu_iso_z_strefą (wymagany jeśli rule_type='time', w przeciwnym razie null/pominięty)",
    "end_time": "znacznik_czasu_iso_z_strefą (wymagany jeśli rule_type='time', w przeciwnym razie null/pominięty)",
    "max_clicks": "liczba całkowita (wymagana i dodatnia jeśli rule_type='clicks', w przeciwnym razie null/pominięty)"
  }
  ```
- **Ciało odpowiedzi (Sukces):**
  ```json
  {
    "id": "uuid",
    "link_id": "uuid",
    "priority": "liczba całkowita",
    "rule_type": "ciąg znaków",
    "target_type": "ciąg znaków",
    "target_value": "ciąg znaków",
    "start_time": "znacznik_czasu_iso_z_strefą | null",
    "end_time": "znacznik_czasu_iso_z_strefą | null",
    "max_clicks": "liczba całkowita | null",
    "current_clicks": 0,
    "created_at": "znacznik_czasu_iso_z_strefą",
    "updated_at": "znacznik_czasu_iso_z_strefą"
  }
  ```
- **Kod sukcesu:** `201 Created`
- **Kody błędów:**
  - `400 Bad Request`: Nieprawidłowy format danych wejściowych (np. brak wymaganych pól dla typu reguły, priorytet niedodatni).
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem linku nadrzędnego.
  - `404 Not Found`: Link nadrzędny o podanym ID nie został znaleziony.
  - `409 Conflict`: Konflikt priorytetu dla tego linku (naruszenie ograniczenia unikalności bazy danych).
  - `422 Unprocessable Entity`: Błąd walidacji.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

#### **Pobierz Listę Reguł**

- **Metoda:** `GET`
- **Ścieżka:** `/links/{id_linku}/rules`
- **Opis:** Pobiera listę wszystkich reguł routingu dla konkretnego linku należącego do uwierzytelnionego użytkownika, posortowaną według priorytetu.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku, którego reguły mają zostać pobrane.
- **Ciało odpowiedzi (Sukces):**
  ```json
  [
    {
      "id": "uuid",
      "link_id": "uuid",
      "priority": "liczba całkowita",
      "rule_type": "ciąg znaków",
      "target_type": "ciąg znaków",
      "target_value": "ciąg znaków",
      "start_time": "znacznik_czasu_iso_z_strefą | null",
      "end_time": "znacznik_czasu_iso_z_strefą | null",
      "max_clicks": "liczba całkowita | null",
      "current_clicks": "liczba całkowita",
      "created_at": "znacznik_czasu_iso_z_strefą",
      "updated_at": "znacznik_czasu_iso_z_strefą"
    }
  ]
  ```
  _(Uwaga: Dla interakcji z HTMX, ten endpoint może zwracać fragment HTML reprezentujący listę reguł)._
- **Kod sukcesu:** `200 OK`
- **Kody błędów:**
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem linku nadrzędnego.
  - `404 Not Found`: Link nadrzędny o podanym ID nie został znaleziony.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

#### **Pobierz Regułę**

- **Metoda:** `GET`
- **Ścieżka:** `/links/{id_linku}/rules/{id_reguly}`
- **Opis:** Pobiera szczegóły konkretnej reguły routingu w obrębie linku należącego do uwierzytelnionego użytkownika.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku nadrzędnego.
  - `id_reguly`: `uuid` (wymagany) - ID reguły do pobrania.
- **Ciało odpowiedzi (Sukces):**
  ```json
  {
    "id": "uuid",
    "link_id": "uuid",
    "priority": "liczba całkowita",
    "rule_type": "ciąg znaków",
    "target_type": "ciąg znaków",
    "target_value": "ciąg znaków",
    "start_time": "znacznik_czasu_iso_z_strefą | null",
    "end_time": "znacznik_czasu_iso_z_strefą | null",
    "max_clicks": "liczba całkowita | null",
    "current_clicks": "liczba całkowita",
    "created_at": "znacznik_czasu_iso_z_strefą",
    "updated_at": "znacznik_czasu_iso_z_strefą"
  }
  ```
- **Kod sukcesu:** `200 OK`
- **Kody błędów:**
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem linku nadrzędnego.
  - `404 Not Found`: Link nadrzędny lub reguła o podanym ID nie została znaleziona.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

#### **Zaktualizuj Regułę**

- **Metoda:** `PATCH`
- **Ścieżka:** `/links/{id_linku}/rules/{id_reguly}`
- **Opis:** Aktualizuje szczegóły konkretnej reguły routingu w obrębie linku należącego do uwierzytelnionego użytkownika.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku nadrzędnego.
  - `id_reguly`: `uuid` (wymagany) - ID reguły do aktualizacji.
- **Ciało żądania:** (Wysyłaj tylko pola do zaktualizowania)
  ```json
  {
    "priority": "liczba całkowita (opcjonalna, dodatnia, unikalna w obrębie linku)",
    "rule_type": "ciąg znaków (opcjonalny, 'time' lub 'clicks')", // Zmiana typu może wymagać dostosowania innych pól
    "target_type": "ciąg znaków (opcjonalny, 'url' lub 'html')", // Zmiana typu może wymagać dostosowania target_value
    "target_value": "ciąg znaków (opcjonalny, poprawny URL jeśli target_type='url', kod HTML jeśli target_type='html')",
    "start_time": "znacznik_czasu_iso_z_strefą | null (opcjonalny, istotny jeśli rule_type='time')",
    "end_time": "znacznik_czasu_iso_z_strefą | null (opcjonalny, istotny jeśli rule_type='time')",
    "max_clicks": "liczba całkowita | null (opcjonalny, dodatni jeśli rule_type='clicks')"
    // current_clicks nie jest aktualizowane przez API
  }
  ```
- **Ciało odpowiedzi (Sukces):** Zaktualizowany obiekt reguły (ta sama struktura co GET Regułę).
- **Kod sukcesu:** `200 OK`
- **Kody błędów:**
  - `400 Bad Request`: Nieprawidłowy format danych wejściowych lub niespójne dane (np. zmiana `rule_type` bez wymaganych pól).
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem linku nadrzędnego.
  - `404 Not Found`: Link nadrzędny lub reguła o podanym ID nie została znaleziona.
  - `409 Conflict`: Konflikt priorytetu, jeśli priorytet jest zmieniany.
  - `422 Unprocessable Entity`: Błąd walidacji.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

#### **Usuń Regułę**

- **Metoda:** `DELETE`
- **Ścieżka:** `/links/{id_linku}/rules/{id_reguly}`
- **Opis:** Usuwa konkretną regułę routingu w obrębie linku należącego do uwierzytelnionego użytkownika.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku nadrzędnego.
  - `id_reguly`: `uuid` (wymagany) - ID reguły do usunięcia.
- **Ciało odpowiedzi (Sukces):** Brak (Puste Ciało).
- **Kod sukcesu:** `204 No Content`
- **Kody błędów:**
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem linku nadrzędnego.
  - `404 Not Found`: Link nadrzędny lub reguła o podanym ID nie została znaleziona.
  - `500 Internal Server Error`: Błąd bazy danych lub inny błąd serwera.

---

### 2.3. Zasób Statystyki (`/links/{id_linku}/stats`)

#### **Pobierz Statystyki Linku**

- **Metoda:** `GET`
- **Ścieżka:** `/links/{id_linku}/stats`
- **Opis:** Pobiera statystyki kliknięć dla konkretnego linku należącego do uwierzytelnionego użytkownika.
- **Uwierzytelnianie:** Wymagane (Token JWT Bearer).
- **Parametry ścieżki:**
  - `id_linku`: `uuid` (wymagany) - ID linku, dla którego pobierane są statystyki.
- **Ciało odpowiedzi (Sukces):**
  ```json
  {
    "link_id": "uuid",
    "alias": "ciąg znaków",
    "total_clicks": "liczba całkowita", // Z routr_links.total_clicks
    "target_clicks": [
      // Zagregowane z routing_rules na podstawie link_id
      {
        "rule_id": "uuid", // Identyfikuje, która reguła spowodowała te kliknięcia
        "target_type": "ciąg znaków", // 'url' lub 'html'
        "target_value_preview": "ciąg znaków", // URL lub podgląd/placeholder dla HTML
        "current_clicks": "liczba całkowita" // Z routing_rules.current_clicks
      }
      // ... potencjalnie więcej celów
    ]
  }
  ```
- **Kod sukcesu:** `200 OK`
- **Kody błędów:**
  - `401 Unauthorized`: Brakujący lub nieprawidłowy token uwierzytelniający.
  - `403 Forbidden`: Użytkownik nie jest właścicielem tego linku.
  - `404 Not Found`: Link o podanym ID nie został znaleziony.
  - `500 Internal Server Error`: Błąd bazy danych podczas agregacji.

---

### 2.4. Zasób Uwierzytelnianie (`/auth`)

_(Uwaga: Te punkty końcowe mogą być prostymi wrapperami wokół funkcji Supabase Auth lub obsługiwane głównie po stronie klienta, w zależności od wybranego przepływu uwierzytelniania)_

#### **Logowanie**

- **Metoda:** `POST`
- **Ścieżka:** `/auth/login`
- **Opis:** Uwierzytelnia użytkownika i zwraca token dostępu (JWT).
- **Uwierzytelnianie:** Niewymagane.
- **Ciało żądania:**
  ```json
  {
    "email": "ciąg znaków (wymagany, poprawny email)",
    "password": "ciąg znaków (wymagany)"
  }
  ```
- **Ciało odpowiedzi (Sukces):** (Struktura zależy od odpowiedzi klienta Supabase, zazwyczaj zawiera access_token, refresh_token, dane użytkownika)
  ```json
  {
    "access_token": "ciąg znaków (jwt)",
    "token_type": "bearer",
    "expires_in": "liczba całkowita",
    "refresh_token": "ciąg znaków",
    "user": {
      "id": "uuid",
      "email": "ciąg znaków"
      // ... inne informacje o użytkowniku z Supabase Auth
    }
  }
  ```
- **Kod sukcesu:** `200 OK`
- **Kody błędów:**
  - `400 Bad Request`: Nieprawidłowy email lub brakujące pola.
  - `401 Unauthorized`: Nieprawidłowy email lub hasło.
  - `422 Unprocessable Entity`: Błąd walidacji.
  - `500 Internal Server Error`: Błąd Supabase Auth lub serwera.

#### **Rejestracja (Opcjonalny Endpoint API)**

- **Metoda:** `POST`
- **Ścieżka:** `/auth/register`
- **Opis:** Rejestruje nowego użytkownika. (Może być obsługiwane po stronie klienta bezpośrednio przez Supabase).
- **Uwierzytelnianie:** Niewymagane.
- **Ciało żądania:**
  ```json
  {
    "email": "ciąg znaków (wymagany, poprawny email)",
    "password": "ciąg znaków (wymagany, spełnia reguły złożoności)"
  }
  ```
- **Ciało odpowiedzi (Sukces):** (Obiekt użytkownika Supabase lub komunikat potwierdzający).
- **Kod sukcesu:** `201 Created` (lub `200 OK` jeśli zwraca obiekt użytkownika).
- **Kody błędów:**
  - `400 Bad Request`: Nieprawidłowy format email/hasła lub brakujące pola.
  - `409 Conflict`: Email już zarejestrowany.
  - `422 Unprocessable Entity`: Błąd walidacji.
  - `500 Internal Server Error`: Błąd Supabase Auth lub serwera.

---

## 3. Uwierzytelnianie i autoryzacja

- **Uwierzytelnianie:** Używa tokenów JWT Bearer wydawanych przez Supabase Auth. Backend API (FastAPI) musi walidować token dostarczony w nagłówku `Authorization: Bearer <token>` dla wszystkich chronionych punktów końcowych.
- **Autoryzacja:** Implementowana głównie za pomocą polityk PostgreSQL Row Level Security (RLS) zdefiniowanych w schemacie bazy danych.
  - Użytkownicy mogą wykonywać operacje CRUD (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) tylko na rekordach `routr_links` i `routing_rules`, gdzie ich `user_id` pasuje do `auth.uid()` z zweryfikowanego JWT.
  - Backend używa JWT do ustalenia tożsamości użytkownika na potrzeby sprawdzania RLS.
  - Publiczny endpoint przekierowania (`/{alias_path:path}`) jest nieuwierzytelniony, a logika backendu uzyskująca dostęp do bazy danych dla tego endpointu _musi_ używać klucza `service_role` Supabase, aby ominąć polityki RLS.

## 4. Walidacja i logika biznesowa

- **Walidacja Danych Wejściowych:**
  - Obsługiwana głównie przez modele Pydantic w FastAPI, w oparciu o podpowiedzi typów i walidatory.
  - Modele odzwierciedlają ograniczenia ze schematu bazy danych:
    - `alias`: Wymagany, unikalny, regex `^[a-z0-9-]+$`, długość 3-64.
    - `default_url`: Opcjonalny, podstawowe sprawdzenie formatu URL.
    - `priority`: Wymagany, dodatnia liczba całkowita.
    - `rule_type` / `target_type`: Wymagane, muszą pasować do wartości ENUM.
    - `target_value`: Wymagane, podstawowe sprawdzenie formatu URL jeśli `target_type` to 'url'. (Sprawdzenie limitu długości HTML odłożone).
    - `start_time` / `end_time`: Wymagane jeśli `rule_type` to 'time'.
    - `max_clicks`: Wymagane i dodatnie jeśli `rule_type` to 'clicks'.
  - Ograniczenia bazy danych (`UNIQUE`, `CHECK`, `NOT NULL`, FK) zapewniają drugą warstwę walidacji. API powinno poprawnie obsługiwać potencjalne błędy naruszenia ograniczeń bazy danych (np. zwracać `409 Conflict` dla naruszeń unikalności, `400 Bad Request` dla naruszeń CHECK).
- **Logika Biznesowa:**
  - **Niezmienność Aliasu:** Endpoint `PATCH /links/{id_linku}` nie pozwala na aktualizację pola `alias`.
  - **Unikalność Priorytetu:** Wymuszana przez ograniczenie `UNIQUE (link_id, priority)` w bazie danych. API obsługuje błąd `409 Conflict`.
  - **Wymagania Pól Reguł:** Logika w modelach Pydantic lub punkcie końcowym API zapewnia, że `start_time`/`end_time` są dostarczone dla reguł typu 'time', a `max_clicks` dla reguł typu 'clicks'. Ograniczenia `CHECK` w bazie danych stanowią zabezpieczenie.
  - **Agregacja Statystyk:** Logika endpointu `GET /links/{id_linku}/stats` pobiera `total_clicks` z `routr_links` i agreguje `current_clicks` z powiązanych `routing_rules`.
  - **Atomowość Zliczania Kliknięć:** Logika przekierowania (poza tym planem API REST) musi implementować atomowe aktualizacje liczników `total_clicks` i `current_clicks` w bazie danych.
  - **Usuwanie Kaskadowe:** `ON DELETE CASCADE` obsługuje usuwanie reguł przy usuwaniu linku. Usuwanie kaskadowe przy usunięciu użytkownika wymaga oddzielnej funkcji Edge.
