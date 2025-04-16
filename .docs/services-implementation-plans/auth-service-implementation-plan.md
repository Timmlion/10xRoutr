# Service Implementation Plan: AuthService

## 1. Przegląd serwisu

Celem `AuthService` jest obsługa logiki biznesowej związanej z uwierzytelnianiem i rejestracją użytkowników. Pełni rolę pośrednika między endpointami API (`/auth/login`, `/auth/register`) a usługą Supabase Auth, wykorzystując bibliotekę `supabase-py`. Odpowiada za wywołanie odpowiednich metod Supabase, obsługę odpowiedzi oraz mapowanie błędów Supabase na niestandardowe wyjątki aplikacyjne, które mogą być następnie łatwo przechwycone i przetworzone przez warstwę API.

## 2. Szczegóły wejścia

- **Rodzaj danych:** Obiekty Pydantic (DTO) reprezentujące dane wejściowe dla operacji logowania i rejestracji.
- **Wymagane dane:**
  - Dla `login_user`: Obiekt `UserLogin` zawierający `email` (EmailStr) i `password` (str).
  - Dla `register_user`: Obiekt `UserRegister` zawierający `email` (EmailStr) i `password` (str, z walidacją np. min_length).
- **Opcjonalne dane:** Brak opcjonalnych danych wejściowych dla tych metod serwisu.

## 3. Wykorzystywane typy

- **Modele Pydantic (DTOs - Wejście):**
  - `schemas.auth.UserLogin`
  - `schemas.auth.UserRegister`
- **Modele Pydantic (DTOs - Wyjście):**
  - `schemas.auth.TokenResponse` (zawiera `schemas.auth.UserInfo`)
  - `schemas.auth.UserRegistrationResponse` (zawiera `schemas.auth.UserInfoMinimal`)
- **Klient Supabase:**
  - `supabase_py_async.AsyncClient` (lub `supabase.Client` dla wersji synchronicznej) - wstrzykiwany do serwisu.
- **Wyjątki Supabase:**
  - `gotrue.errors.AuthApiError` (lub specyficzne podtypy, jeśli biblioteka je dostarcza) - do przechwytywania błędów z Supabase Auth.
- **Niestandardowe Wyjątki Aplikacyjne (do zdefiniowania w `services.custom_exceptions`):**
  - `ServiceException` (klasa bazowa)
  - `AuthenticationFailedException(ServiceException)`: Dla nieprawidłowych danych logowania.
  - `EmailExistsException(ServiceException)`: Dla próby rejestracji z zajętym adresem email.
  - `PasswordPolicyException(ServiceException)`: Dla hasła niespełniającego wymagań.
  - `AuthServiceException(ServiceException)`: Dla innych błędów związanych z usługą autentykacji.

## 4. Szczegóły działania serwisu

- **`login_user(login_data: UserLogin)`:**
  1.  Wywołuje metodę `supabase.auth.sign_in_with_password` klienta Supabase, przekazując email i hasło z obiektu `login_data`.
  2.  W przypadku sukcesu, przetwarza odpowiedź Supabase (np. obiekt `AuthResponse`), tworzy i zwraca obiekt `TokenResponse`.
  3.  W przypadku błędu uwierzytelnienia (np. nieprawidłowe hasło/email) przechwytuje wyjątek `AuthApiError` i zgłasza niestandardowy wyjątek `AuthenticationFailedException`.
  4.  W przypadku innych błędów komunikacji z Supabase, przechwytuje `AuthApiError` lub inne wyjątki i zgłasza `AuthServiceException`.
- **`register_user(register_data: UserRegister)`:**
  1.  Wywołuje metodę `supabase.auth.sign_up` klienta Supabase, przekazując email i hasło z obiektu `register_data`.
  2.  W przypadku sukcesu, przetwarza odpowiedź Supabase (np. obiekt `SignUpResponse`), tworzy i zwraca obiekt `UserRegistrationResponse`.
  3.  W przypadku błędu wskazującego na zajęty email, przechwytuje odpowiedni `AuthApiError` i zgłasza `EmailExistsException`.
  4.  W przypadku błędu wskazującego na naruszenie polityki haseł, przechwytuje odpowiedni `AuthApiError` i zgłasza `PasswordPolicyException`.
  5.  W przypadku innych błędów komunikacji, przechwytuje `AuthApiError` lub inne wyjątki i zgłasza `AuthServiceException`.

## 5. Przepływ danych

1.  **Endpoint API (`/auth/login` lub `/auth/register`)** otrzymuje żądanie HTTP i waliduje ciało żądania za pomocą odpowiedniego modelu Pydantic (`UserLogin` lub `UserRegister`).
2.  Handler endpointu wywołuje odpowiednią metodę (`login_user` lub `register_user`) w instancji `AuthService`, przekazując zwalidowany obiekt DTO.
3.  **Metoda `AuthService`** wywołuje odpowiednią metodę (`sign_in_with_password` lub `sign_up`) wstrzykniętego klienta **`supabase-py`**.
4.  Klient `supabase-py` komunikuje się z **backendem Supabase Auth** (przez HTTP).
5.  Backend Supabase Auth przetwarza żądanie (sprawdza dane, tworzy użytkownika/sesję) i zwraca odpowiedź lub błąd do klienta `supabase-py`.
6.  Klient `supabase-py` zwraca wynik (dane lub wyjątek) do metody `AuthService`.
7.  **Metoda `AuthService`** przetwarza wynik:
    - W przypadku sukcesu: mapuje dane Supabase na odpowiedni model Pydantic (`TokenResponse` lub `UserRegistrationResponse`) i zwraca go do handlera endpointu.
    - W przypadku błędu Supabase: przechwytuje wyjątek `AuthApiError`, analizuje go i zgłasza odpowiedni niestandardowy wyjątek aplikacyjny (`AuthenticationFailedException`, `EmailExistsException`, `PasswordPolicyException`, `AuthServiceException`).
8.  **Handler endpointu API** przechwytuje niestandardowe wyjątki z `AuthService`:
    - Mapuje je na odpowiednie `HTTPException` z właściwym kodem statusu (`401`, `409`, `400`, `500`) i szczegółowym komunikatem dla klienta.
    - W przypadku sukcesu, serializuje zwrócony obiekt Pydantic do JSON i wysyła odpowiedź HTTP (`200 OK` lub `201 Created`).

## 6. Względy bezpieczeństwa

- **Obsługa Poświadczeń:** Serwis jedynie przekazuje email i hasło do Supabase Auth. Nie przechowuje, ani nie loguje haseł w postaci jawnej. Należy upewnić się, że logowanie na poziomie aplikacji nie rejestruje przypadkowo wrażliwych danych z obiektów żądań.
- **Komunikacja z Supabase:** Komunikacja z Supabase powinna odbywać się przez HTTPS (zapewniane przez `supabase-py` i konfigurację Supabase).
- **Walidacja Wejścia:** Chociaż FastAPI z Pydantic dokonuje walidacji formatu (np. email), serwis polega na Supabase Auth w zakresie walidacji istnienia użytkownika, poprawności hasła i polityki złożoności haseł.
- **Obsługa Błędów:** Należy unikać zwracania zbyt szczegółowych informacji o błędach wewnętrznych Supabase do klienta API. Niestandardowe wyjątki pomagają w abstrakcji i kontrolowaniu tego, co jest ujawniane. Błędy 401 dla logowania powinny być generyczne. Błędy 409/400 dla rejestracji mogą być bardziej specyficzne.
- **Supabase Client:** AuthService używa standardowego klienta Supabase (zazwyczaj inicjalizowanego kluczem `anon`, ponieważ te operacje nie wymagają uwierzytelnienia _przed_ ich wykonaniem).

## 7. Obsługa błędów

Serwis powinien przechwytywać wyjątki z biblioteki `supabase-py` (głównie `gotrue.errors.AuthApiError`) i mapować je na niestandardowe wyjątki aplikacyjne:

- **Nieprawidłowe dane logowania:** (`sign_in_with_password` zwraca błąd) -> Zgłoś `AuthenticationFailedException`. Handler API zwróci `401 Unauthorized`.
- **Email już istnieje:** (`sign_up` zwraca błąd o konflikcie email) -> Zgłoś `EmailExistsException`. Handler API zwróci `409 Conflict`.
- **Hasło nie spełnia wymagań:** (`sign_up` zwraca błąd polityki haseł) -> Zgłoś `PasswordPolicyException`. Handler API zwróci `400 Bad Request`.
- **Inne błędy Supabase Auth/Sieciowe:** (np. problem z połączeniem, timeout, błąd wewnętrzny Supabase) -> Zgłoś `AuthServiceException` (lub bardziej generyczny `ServiceException`). Handler API zwróci `500 Internal Server Error`.
- **Nieoczekiwane błędy Pythona:** Powinny być przechwytywane wyżej (np. w middleware lub globalnym handlerze wyjątków FastAPI) i skutkować `500 Internal Server Error`, z logowaniem szczegółów.

Wszystkie błędy (zwłaszcza 500) powinny być logowane po stronie serwera wraz z odpowiednim kontekstem (np. trace ID, jeśli używane) w celu ułatwienia debugowania.

## 8. Rozważania dotyczące wydajności

- Wydajność tego serwisu jest niemal całkowicie zależna od **czasu odpowiedzi usługi Supabase Auth**.
- Operacje logowania i rejestracji obejmują zapytania do bazy danych użytkowników Supabase oraz potencjalnie operacje kryptograficzne (weryfikacja hasha, generowanie tokenu).
- Serwis sam w sobie dodaje minimalny narzut (mapowanie danych, obsługa wyjątków).
- **Strategie Optymalizacji (głównie poza serwisem):**
  - Zapewnienie dobrej łączności sieciowej między serwerem API a Supabase.
  - Implementacja rate limitingu na poziomie API, aby zapobiec nadużyciom wpływającym na wydajność Supabase Auth.

## 9. Etapy wdrożenia

1.  **Utworzenie Pliku Serwisu:** Stwórz plik `src/services/auth_service.py`.
2.  **Zdefiniowanie Wyjątków:** Upewnij się, że niestandardowe wyjątki (`AuthenticationFailedException`, `EmailExistsException`, `PasswordPolicyException`, `AuthServiceException`) są zdefiniowane (np. w `src/services/custom_exceptions.py`).
3.  **Implementacja Klasy `AuthService`:**
    - Dodaj metodę `__init__(self, supabase: AsyncClient)` przyjmującą klienta Supabase.
4.  **Implementacja Metody `login_user`:**
    - Dodaj metodę `async def login_user(self, login_data: UserLogin) -> TokenResponse`.
    - Wywołaj `supabase.auth.sign_in_with_password`.
    - Dodaj blok `try...except AuthApiError` do przechwytywania błędów logowania i zgłaszania `AuthenticationFailedException` lub `AuthServiceException`.
    - W bloku `try` (po sukcesie) zmapuj odpowiedź Supabase na `TokenResponse` i zwróć ją.
5.  **Implementacja Metody `register_user`:**
    - Dodaj metodę `async def register_user(self, register_data: UserRegister) -> UserRegistrationResponse`.
    - Wywołaj `supabase.auth.sign_up`.
    - Dodaj blok `try...except AuthApiError`. Wewnątrz bloku `except` sprawdź szczegóły błędu (kod, komunikat), aby rozróżnić między konfliktem email (zgłoś `EmailExistsException`), naruszeniem polityki haseł (zgłoś `PasswordPolicyException`), a innymi błędami (zgłoś `AuthServiceException`).
    - W bloku `try` zmapuj odpowiedź Supabase na `UserRegistrationResponse` i zwróć ją.
6.  **Dodanie Logowania:** Dodaj logowanie błędów w blokach `except` (przed zgłoszeniem niestandardowego wyjątku).
7.  **Testy Jednostkowe:**
    - Napisz testy jednostkowe dla `AuthService` w `tests/services/test_auth_service.py`.
    - Użyj `pytest-mock` (lub `unittest.mock`), aby zamockować metody `supabase.auth.sign_in_with_password` i `supabase.auth.sign_up`.
    - Testuj scenariusze sukcesu dla obu metod, sprawdzając poprawność zwracanych obiektów DTO.
    - Testuj scenariusze błędów, symulując rzucanie `AuthApiError` przez mocki Supabase (z różnymi kodami/komunikatami) i weryfikując, czy serwis zgłasza odpowiednie niestandardowe wyjątki.
