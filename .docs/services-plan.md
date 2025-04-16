# Specyfikacja Warstwy Serwisowej - routr (MVP)

Ten dokument opisuje projekt i oczekiwane zachowanie warstwy serwisowej dla aplikacji _routr_ (MVP). Warstwa serwisowa zawiera logikę biznesową, koordynuje interakcje z bazą danych (za pośrednictwem klienta Supabase) i jest wywoływana przez handlery endpointów API (FastAPI).

## 1. Przegląd

Warstwa serwisowa jest podzielona na moduły odpowiadające głównym domenom funkcjonalnym aplikacji:

- **AuthService:** Obsługa logiki związanej z uwierzytelnianiem użytkowników (logowanie, rejestracja) za pomocą Supabase Auth.
- **LinkService:** Zarządzanie cyklem życia linków (`routr_links`), w tym operacje CRUD oraz pobieranie powiązanych reguł i statystyk.
- **RuleService:** Zarządzanie cyklem życia reguł (`routing_rules`), w tym operacje CRUD dla reguł powiązanych z konkretnym linkiem.
- **RedirectionService:** Implementacja kluczowej logiki publicznego przekierowania na podstawie aliasu, w tym ewaluacja reguł i inkrementacja liczników.

## 2. Usługi

---

### 2.1. AuthService

Odpowiedzialny za interakcje z Supabase Auth.

#### **Metoda: `login_user`**

- **Sygnatura:** `async def login_user(self, login_data: UserLogin) -> TokenResponse`
- **Opis:** Uwierzytelnia użytkownika na podstawie emaila i hasła przy użyciu Supabase Auth.
- **Parametry wejściowe:**
  - `login_data` (`UserLogin`): Obiekt Pydantic zawierający `email` i `password`.
- **Wartość zwracana (Sukces):**
  - `TokenResponse`: Obiekt Pydantic zawierający tokeny (`access_token`, `refresh_token`, etc.) i informacje o użytkowniku zwrócone przez Supabase.
- **Logika Biznesowa / Kroki:**
  1.  Wywołaj `supabase.auth.sign_in_with_password` z danymi z `login_data`.
  2.  Przechwyć odpowiedź sukcesu z Supabase.
  3.  Zmapuj dane z odpowiedzi Supabase (np. `AuthResponse`) na model Pydantic `TokenResponse`.
  4.  Zwróć obiekt `TokenResponse`.
- **Potencjalne Wyjątki:**
  - `AuthenticationFailedException` (niestandardowy): Jeśli Supabase zwróci błąd wskazujący na nieprawidłowe dane logowania (opakowuje np. `AuthApiError`).
  - `ServiceException` / `DatabaseException` (niestandardowy): Dla innych błędów komunikacji z Supabase Auth lub nieoczekiwanych problemów.

#### **Metoda: `register_user`**

- **Sygnatura:** `async def register_user(self, register_data: UserRegister) -> UserRegistrationResponse`
- **Opis:** Rejestruje nowego użytkownika przy użyciu Supabase Auth.
- **Parametry wejściowe:**
  - `register_data` (`UserRegister`): Obiekt Pydantic zawierający `email` i `password` (spełniający wymogi złożoności).
- **Wartość zwracana (Sukces):**
  - `UserRegistrationResponse`: Obiekt Pydantic zawierający informacje o nowo utworzonym użytkowniku (zgodnie z odpowiedzią Supabase).
- **Logika Biznesowa / Kroki:**
  1.  Wywołaj `supabase.auth.sign_up` z danymi z `register_data`.
  2.  Przechwyć odpowiedź sukcesu z Supabase (np. `SignUpResponse`).
  3.  Zmapuj dane z odpowiedzi Supabase na model Pydantic `UserRegistrationResponse`.
  4.  Zwróć obiekt `UserRegistrationResponse`.
- **Potencjalne Wyjątki:**
  - `EmailExistsException` (niestandardowy): Jeśli Supabase zwróci błąd wskazujący, że email jest już zajęty (opakowuje np. `AuthApiError`).
  - `PasswordPolicyException` (niestandardowy): Jeśli hasło nie spełnia wymagań Supabase (opakowuje np. `AuthApiError`).
  - `ServiceException` / `DatabaseException` (niestandardowy): Dla innych błędów komunikacji z Supabase Auth.

---

### 2.2. LinkService

Odpowiedzialny za operacje na zasobie `routr_links` oraz powiązane odczyty. Używa klienta Supabase z kontekstem JWT użytkownika.

#### **Metoda: `create_link`**

- **Sygnatura:** `async def create_link(self, link_data: LinkCreate, user_id: UUID) -> LinkResponse`
- **Opis:** Tworzy nowy rekord `routr_links` w bazie danych dla podanego użytkownika.
- **Parametry wejściowe:**
  - `link_data` (`LinkCreate`): Zwalidowane dane dla nowego linku (`alias`, `default_url`).
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika tworzącego link.
- **Wartość zwracana (Sukces):**
  - `LinkResponse`: Obiekt Pydantic reprezentujący nowo utworzony link (wraz z `id`, `created_at` itp.).
- **Logika Biznesowa / Kroki:**
  1.  Przygotuj słownik danych do wstawienia, zawierający `alias`, `default_url` (z `link_data`) oraz `user_id`.
  2.  Wykonaj zapytanie `insert` do tabeli `routr_links` za pomocą klienta Supabase (z kontekstem użytkownika, RLS `WITH CHECK` się zastosuje). Użyj opcji `.select("*").single()` aby od razu otrzymać wstawiony rekord.
  3.  Zmapuj zwrócone dane na model `LinkResponse`.
  4.  Zwróć obiekt `LinkResponse`.
- **Potencjalne Wyjątki:**
  - `AliasConflictException` (niestandardowy): Jeśli zapytanie `insert` zwróci błąd naruszenia ograniczenia unikalności dla `alias` (kod `23505`).
  - `DatabaseException` (niestandardowy): Dla innych błędów bazy danych podczas operacji `insert`.

#### **Metoda: `get_links_paginated`**

- **Sygnatura:** `async def get_links_paginated(self, user_id: UUID, page: int, page_size: int) -> PaginatedLinkResponse`
- **Opis:** Pobiera paginowaną listę linków należących do danego użytkownika.
- **Parametry wejściowe:**
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
  - `page` (`int`): Numer strony (>= 1).
  - `page_size` (`int`): Liczba elementów na stronie (np. 1-100).
- **Wartość zwracana (Sukces):**
  - `PaginatedLinkResponse`: Obiekt Pydantic zawierający listę linków (`items`), całkowitą liczbę linków (`total`), numer strony (`page`) i rozmiar strony (`page_size`).
- **Logika Biznesowa / Kroki:**
  1.  Oblicz `offset = (page - 1) * page_size`.
  2.  Wykonaj zapytanie `select` do tabeli `routr_links` z klientem Supabase (RLS `USING` zastosuje filtr `user_id`).
  3.  Użyj `.range(offset, offset + page_size - 1)` do paginacji.
  4.  Użyj `.order('created_at', desc=True)` dla spójnego sortowania.
  5.  Użyj opcji `count='exact'` (lub odpowiednika w `supabase-py v2+`), aby uzyskać całkowitą liczbę pasujących rekordów (`total`) w jednym zapytaniu.
  6.  Zmapuj pobrane rekordy (`response.data`) na listę obiektów `LinkResponse`.
  7.  Skonstruuj i zwróć obiekt `PaginatedLinkResponse` używając pobranej listy, `response.count` oraz wejściowych `page` i `page_size`.
- **Potencjalne Wyjątki:**
  - `DatabaseException` (niestandardowy): Dla błędów bazy danych podczas operacji `select` lub `count`.

#### **Metoda: `get_link_by_id`**

- **Sygnatura:** `async def get_link_by_id(self, link_id: UUID, user_id: UUID) -> LinkResponse`
- **Opis:** Pobiera szczegóły konkretnego linku, weryfikując jednocześnie jego przynależność do użytkownika.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID szukanego linku.
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):**
  - `LinkResponse`: Obiekt Pydantic reprezentujący znaleziony link.
- **Logika Biznesowa / Kroki:**
  1.  Wykonaj zapytanie `select` do tabeli `routr_links` z klientem Supabase.
  2.  Filtruj po `id = link_id`. RLS `USING (auth.uid() = user_id)` automatycznie zapewni sprawdzenie własności.
  3.  Użyj `.maybe_single()` aby oczekiwać jednego lub żadnego wyniku.
  4.  Jeśli dane (`response.data`) zostaną zwrócone, zmapuj je na `LinkResponse` i zwróć.
  5.  Jeśli dane nie zostaną zwrócone (link nie istnieje lub nie należy do użytkownika), zgłoś `NotFoundException`.
- **Potencjalne Wyjątki:**
  - `NotFoundException` (niestandardowy): Jeśli link o podanym ID nie istnieje lub nie należy do użytkownika.
  - `DatabaseException` (niestandardowy): Dla innych błędów bazy danych.

#### **Metoda: `update_link`**

- **Sygnatura:** `async def update_link(self, link_id: UUID, update_data: LinkUpdate, user_id: UUID) -> LinkResponse`
- **Opis:** Aktualizuje dane (`default_url`) istniejącego linku należącego do użytkownika.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID linku do aktualizacji.
  - `update_data` (`LinkUpdate`): Obiekt Pydantic zawierający pola do aktualizacji (tylko `default_url` w MVP).
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):**
  - `LinkResponse`: Obiekt Pydantic reprezentujący zaktualizowany link.
- **Logika Biznesowa / Kroki:**
  1.  _(Opcjonalnie, ale zalecane dla lepszej obsługi błędów)_ Najpierw sprawdź, czy link istnieje i należy do użytkownika wykonując `select id` z filtrem `id = link_id`. RLS `USING` sprawdzi własność. Jeśli nie znaleziono, zgłoś `NotFoundException`.
  2.  Przygotuj słownik `db_update_payload` zawierający tylko te pola z `update_data`, które zostały faktycznie przesłane przez użytkownika (`update_data.model_dump(exclude_unset=True)`).
  3.  Jeśli `db_update_payload` jest pusty, zwróć bieżący stan linku bez wykonywania update (lub zgłoś błąd, zależnie od wymagań).
  4.  Wykonaj zapytanie `update` do tabeli `routr_links`, ustawiając pola z `db_update_payload`.
  5.  Filtruj po `id = link_id`. RLS `USING` dodatkowo zabezpieczy operację.
  6.  Użyj opcji `.select("*").single()`, aby otrzymać zaktualizowany rekord.
  7.  Jeśli dane (`response.data`) zostaną zwrócone, zmapuj je na `LinkResponse` i zwróć.
  8.  Jeśli `update` nie zwrócił danych (co nie powinno się zdarzyć, jeśli krok 1 był wykonany), zgłoś `NotFoundException`.
- **Potencjalne Wyjątki:**
  - `NotFoundException` (niestandardowy): Jeśli link o podanym ID nie istnieje lub nie należy do użytkownika.
  - `DatabaseException` (niestandardowy): Dla błędów bazy danych podczas operacji `update` lub `select`.

#### **Metoda: `delete_link`**

- **Sygnatura:** `async def delete_link(self, link_id: UUID, user_id: UUID) -> None`
- **Opis:** Usuwa link należący do użytkownika. Powiązane reguły zostaną usunięte kaskadowo przez bazę danych.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID linku do usunięcia.
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):** `None`.
- **Logika Biznesowa / Kroki:**
  1.  Wykonaj zapytanie `delete` do tabeli `routr_links` z klientem Supabase.
  2.  Filtruj po `id = link_id`. RLS `USING (auth.uid() = user_id)` zapewni, że użytkownik może usunąć tylko swój link.
  3.  Sprawdź wynik operacji (np. `response.count`). Jeśli `count == 0`, oznacza to, że link nie istniał lub nie należał do użytkownika - zgłoś `NotFoundException`.
  4.  Jeśli `count == 1`, operacja się powiodła, zwróć `None`.
- **Potencjalne Wyjątki:**
  - `NotFoundException` (niestandardowy): Jeśli link o podanym ID nie istnieje lub nie należy do użytkownika (delete zwrócił count 0).
  - `DatabaseException` (niestandardowy): Dla innych błędów bazy danych podczas operacji `delete`.

#### **Metoda: `get_link_statistics`** (Przeniesiona z dedykowanego serwisu dla prostoty MVP)

- **Sygnatura:** `async def get_link_statistics(self, link_id: UUID, user_id: UUID) -> LinkStatsResponse`
- **Opis:** Pobiera statystyki kliknięć dla konkretnego linku użytkownika.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID linku.
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):**
  - `LinkStatsResponse`: Obiekt Pydantic zawierający statystyki.
- **Logika Biznesowa / Kroki:**
  1.  Wykonaj `select id, alias, total_clicks` z `routr_links` filtrując po `id=link_id`. RLS `USING` sprawdzi własność. Jeśli nie znaleziono, zgłoś `NotFoundException`. Zapamiętaj `alias` i `total_clicks`.
  2.  Wykonaj `select id as rule_id, target_type, target_value, current_clicks` z `routing_rules` filtrując po `link_id=link_id` i sortując po `priority asc`. RLS `USING` również się tu zastosuje.
  3.  Przetwórz wyniki reguł: dla każdej reguły wygeneruj `target_value_preview` (URL lub placeholder dla HTML) i stwórz listę obiektów/słowników `TargetClickStat`.
  4.  Skonstruuj i zwróć obiekt `LinkStatsResponse` używając danych linku i przetworzonej listy statystyk reguł.
- **Potencjalne Wyjątki:**
  - `NotFoundException` (niestandardowy): Jeśli link nadrzędny nie istnieje lub nie należy do użytkownika.
  - `DatabaseException` (niestandardowy): Dla błędów bazy danych podczas pobierania danych.

---

### 2.3. RuleService

Odpowiedzialny za operacje CRUD na zasobie `routing_rules`. Używa klienta Supabase z kontekstem JWT użytkownika. Wymaga sprawdzenia własności linku nadrzędnego.

#### **Metoda: `add_rule_to_link`**

- **Sygnatura:** `async def add_rule_to_link(self, link_id: UUID, rule_data: RuleCreate, user_id: UUID) -> RuleResponse`
- **Opis:** Dodaje nową regułę do istniejącego linku należącego do użytkownika.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID linku nadrzędnego.
  - `rule_data` (`RuleCreate`): Zwalidowane dane dla nowej reguły.
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):**
  - `RuleResponse`: Obiekt Pydantic reprezentujący nowo utworzoną regułę.
- **Logika Biznesowa / Kroki:**
  1.  **Sprawdź własność linku nadrzędnego:** Wykonaj `select id` z `routr_links` filtrując po `id = link_id`. RLS `USING` sprawdzi własność. Jeśli nie znaleziono, zgłoś `ParentLinkNotFoundException`.
  2.  Przygotuj słownik danych do wstawienia, zawierający pola z `rule_data` oraz `link_id`.
  3.  Wykonaj zapytanie `insert` do tabeli `routing_rules`. Użyj `.select("*").single()`.
  4.  Przechwyć błąd naruszenia unikalności `(link_id, priority)` (kod `23505`) i zgłoś `PriorityConflictException`.
  5.  Przechwyć inne błędy DB i zgłoś `DatabaseException`.
  6.  Zmapuj zwrócone dane na `RuleResponse` i zwróć.
- **Potencjalne Wyjątki:**
  - `ParentLinkNotFoundException` (niestandardowy): Jeśli link nadrzędny nie istnieje lub nie należy do użytkownika.
  - `PriorityConflictException` (niestandardowy): Jeśli priorytet jest już zajęty dla tego linku.
  - `DatabaseException` (niestandardowy): Dla innych błędów DB.

#### **Metoda: `get_rules_for_link`** (Alternatywnie, może być w `LinkService`)

- **Sygnatura:** `async def get_rules_for_link(self, link_id: UUID, user_id: UUID) -> List[RuleResponse]`
- **Opis:** Pobiera listę wszystkich reguł dla danego linku, sortowanych wg priorytetu.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID linku nadrzędnego.
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):**
  - `List[RuleResponse]`: Lista obiektów Pydantic reprezentujących reguły.
- **Logika Biznesowa / Kroki:**
  1.  **Sprawdź własność linku nadrzędnego** (jak w `add_rule_to_link`). Jeśli błąd, zgłoś `ParentLinkNotFoundException`.
  2.  Wykonaj `select *` z `routing_rules` filtrując po `link_id = link_id` i sortując `order by priority asc`. RLS `USING` zastosuje się dodatkowo.
  3.  Zmapuj wyniki na listę `RuleResponse` i zwróć.
- **Potencjalne Wyjątki:**
  - `ParentLinkNotFoundException`.
  - `DatabaseException`.

#### **Metoda: `get_rule_details`**

- **Sygnatura:** `async def get_rule_details(self, link_id: UUID, rule_id: UUID, user_id: UUID) -> RuleResponse`
- **Opis:** Pobiera szczegóły pojedynczej reguły, weryfikując przynależność do linku i użytkownika.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID linku nadrzędnego.
  - `rule_id` (`UUID`): ID szukanej reguły.
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):**
  - `RuleResponse`: Obiekt Pydantic reprezentujący znalezioną regułę.
- **Logika Biznesowa / Kroki:**
  1.  Wykonaj `select *` z `routing_rules` filtrując po `id = rule_id` ORAZ `link_id = link_id`. RLS `USING` zapewni sprawdzenie własności nadrzędnego linku.
  2.  Użyj `.maybe_single()`.
  3.  Jeśli dane zwrócone, zmapuj na `RuleResponse` i zwróć.
  4.  Jeśli nie znaleziono, zgłoś `NotFoundException`.
- **Potencjalne Wyjątki:**
  - `NotFoundException` (niestandardowy): Jeśli reguła nie istnieje, nie należy do podanego linku lub użytkownik nie jest właścicielem linku.
  - `DatabaseException`.

#### **Metoda: `update_rule`**

- **Sygnatura:** `async def update_rule(self, link_id: UUID, rule_id: UUID, update_data: RuleUpdate, user_id: UUID) -> RuleResponse`
- **Opis:** Aktualizuje dane istniejącej reguły należącej do użytkownika.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID linku nadrzędnego.
  - `rule_id` (`UUID`): ID reguły do aktualizacji.
  - `update_data` (`RuleUpdate`): Obiekt Pydantic z polami do aktualizacji.
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):**
  - `RuleResponse`: Obiekt Pydantic reprezentujący zaktualizowaną regułę.
- **Logika Biznesowa / Kroki:**
  1.  **Pobierz bieżący stan reguły:** Wykonaj `select *` (jak w `get_rule_details`), aby sprawdzić istnienie i własność. Jeśli nie znaleziono, zgłoś `NotFoundException`.
  2.  **Połącz dane:** Stwórz słownik `final_state` łącząc bieżące dane reguły z danymi z `update_data` (tylko polami, które zostały przesłane).
  3.  **Walidacja spójności:** Sprawdź w `final_state`, czy wymagane pola są obecne dla docelowego `rule_type` (np. `start/end_time` dla 'time', `max_clicks` dla 'clicks'), czy `end_time > start_time`, czy format `target_value` jest zgodny z `target_type`. Jeśli niespójne, zgłoś `ValidationException` lub `BadRequestException`.
  4.  **Przygotuj payload do update:** Stwórz słownik `db_update_payload` zawierający tylko te pola z `update_data`, które faktycznie mają być zmienione. Dodatkowo, jeśli `rule_type` się zmienił, wyzeruj (ustaw na NULL) pola, które stały się nieistotne (np. `max_clicks` jeśli nowym typem jest 'time').
  5.  Jeśli `db_update_payload` nie jest pusty, wykonaj `update` na `routing_rules` filtrując po `id = rule_id`. RLS `USING` dodatkowo zabezpieczy. Użyj `.select("*").single()`.
  6.  Przechwyć błąd naruszenia unikalności `(link_id, priority)` (kod `23505`), jeśli `priority` było aktualizowane, i zgłoś `PriorityConflictException`.
  7.  Przechwyć inne błędy DB i zgłoś `DatabaseException`.
  8.  Jeśli update się powiódł, zwróć zmapowany `RuleResponse` z zwróconych danych. Jeśli `db_update_payload` był pusty, zwróć `RuleResponse` na podstawie danych z kroku 1.
- **Potencjalne Wyjątki:**
  - `NotFoundException`.
  - `ValidationException`/`BadRequestException` (niestandardowy): Niespójne dane po połączeniu update'u.
  - `PriorityConflictException`.
  - `DatabaseException`.

#### **Metoda: `delete_rule`**

- **Sygnatura:** `async def delete_rule(self, link_id: UUID, rule_id: UUID, user_id: UUID) -> None`
- **Opis:** Usuwa konkretną regułę należącą do użytkownika.
- **Parametry wejściowe:**
  - `link_id` (`UUID`): ID linku nadrzędnego.
  - `rule_id` (`UUID`): ID reguły do usunięcia.
  - `user_id` (`UUID`): ID uwierzytelnionego użytkownika.
- **Wartość zwracana (Sukces):** `None`.
- **Logika Biznesowa / Kroki:**
  1.  Wykonaj `delete` z `routing_rules` filtrując po `id = rule_id` ORAZ `link_id = link_id`. RLS `USING` zastosuje się dodatkowo.
  2.  Sprawdź `response.count`. Jeśli 0, zgłoś `NotFoundException`.
  3.  Jeśli 1, zwróć `None`.
- **Potencjalne Wyjątki:**
  - `NotFoundException`.
  - `DatabaseException`.

---

### 2.4. RedirectionService

Odpowiedzialny za logikę publicznego endpointu `/{alias_path:path}`. Używa klienta Supabase skonfigurowanego z kluczem `service_role`.

#### **Metoda: `process_redirection`**

- **Sygnatura:** `async def process_redirection(self, alias_path: str) -> Tuple[RedirectionAction, Optional[str]]` (gdzie `RedirectionAction` to Enum)
- **Opis:** Główna metoda obsługująca przekierowanie. Znajduje link, inkrementuje liczniki, ewaluuje reguły i zwraca akcję do wykonania.
- **Parametry wejściowe:**
  - `alias_path` (`str`): Alias z ścieżki URL.
- **Wartość zwracana (Sukces):**
  - Krotka `(RedirectionAction, Wartość | None)`:
    - `RedirectionAction`: Enum wskazujący typ akcji (np. `REDIRECT_URL`, `SERVE_HTML`, `REDIRECT_DEFAULT`, `REDIRECT_GLOBAL_FALLBACK`).
    - `Wartość | None`: Docelowy URL (dla przekierowań) lub zawartość HTML, lub `None` (dla globalnego fallbacku).
- **Logika Biznesowa / Kroki:** (Jak opisano szczegółowo w Planie Implementacji API dla tego endpointu)
  1.  Znajdź `routr_links` po `alias` używając klienta `service_role`. Jeśli nie ma, zgłoś `LinkNotFoundException`. Zapamiętaj `link_id`, `default_url`.
  2.  Atomowo inkrementuj `total_clicks` dla `link_id`. Loguj błąd, ale kontynuuj.
  3.  Pobierz `routing_rules` dla `link_id` posortowane po `priority` używając klienta `service_role`.
  4.  Iteruj przez reguły:
      - Sprawdź warunek `rule_type` (czas lub kliknięcia).
      - Jeśli warunek spełniony:
        - Atomowo inkrementuj `current_clicks` dla tej reguły (`rule_id`). Loguj błąd, ale kontynuuj.
        - Jeśli `target_type == 'url'`, zwróć `(RedirectionAction.REDIRECT_URL, target_value)`.
        - Jeśli `target_type == 'html'`, zwróć `(RedirectionAction.SERVE_HTML, target_value)`.
        - Zakończ pętlę i przetwarzanie.
  5.  Jeśli pętla zakończona bez dopasowania:
      - Jeśli `default_url` istnieje, zwróć `(RedirectionAction.REDIRECT_DEFAULT, default_url)`.
      - W przeciwnym razie, zwróć `(RedirectionAction.REDIRECT_GLOBAL_FALLBACK, None)`.
- **Potencjalne Wyjątki:**
  - `LinkNotFoundException` (niestandardowy): Jeśli alias nie zostanie znaleziony.
  - `DatabaseException` (niestandardowy): Dla błędów podczas zapytań SELECT lub UPDATE liczników.

## 3. Ogólne Założenia

- **Wstrzykiwanie Zależności:** Usługi będą otrzymywać instancję klienta Supabase (odpowiednio skonfigurowanego - z JWT użytkownika lub `service_role`) poprzez mechanizm wstrzykiwania zależności FastAPI (`Depends`).
- **Obsługa Błędów:** Usługi zgłaszają niestandardowe, semantyczne wyjątki (np. `NotFoundException`, `AliasConflictException`), które są następnie mapowane na odpowiednie `HTTPException` w warstwie API (endpoint handlers). Błędy bazy danych są opakowywane w ogólny `DatabaseException`.
- **Atomowość Liczników:** Logika inkrementująca liczniki (`total_clicks`, `current_clicks`) musi używać atomowych operacji UPDATE w bazie danych (`SET counter = counter + 1`), aby zapewnić poprawność przy współbieżnych żądaniach. Odpowiedzialność za to leży w implementacji metod serwisowych.
- **Kontekst Użytkownika vs. Rola Serwisowa:** Usługi zarządzania (LinkService, RuleService) działają w kontekście uwierzytelnionego użytkownika (korzystając z RLS). RedirectionService działa z uprawnieniami `service_role`, omijając RLS dla publicznego dostępu.
