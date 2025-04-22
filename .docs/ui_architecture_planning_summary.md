# Architektura UI dla routr (MVP)

## 1. Przegląd struktury UI

Architektura interfejsu użytkownika (UI) dla aplikacji "routr" (MVP) opiera się na podejściu serwerowego renderowania HTML z dynamicznymi aktualizacjami realizowanymi za pomocą HTMX. Backend FastAPI będzie serwował szablony Jinja2, a Bootstrap 5 (przez CDN) zapewni bazę dla stylizacji i komponentów UI.

Struktura UI składa się z kilku głównych widoków: publicznej strony docelowej (Landing Page), stron uwierzytelniania (Logowanie, Rejestracja), głównego panelu użytkownika (Dashboard / Lista Linków) oraz widoku szczegółów/edycji linku z zagnieżdżonymi zakładkami dla zarządzania regułami i przeglądania statystyk. Kluczowe operacje CRUD (tworzenie/edycja linków i reguł) będą realizowane za pomocą modali Bootstrapa i żądań HTMX, minimalizując potrzebę przeładowywania całej strony.

Nawigacja dla zalogowanych użytkowników będzie oparta na stałej górnej belce (Navbar), zapewniającej dostęp do kluczowych sekcji i akcji. Zarządzanie stanem sesji opiera się na tokenie JWT przechowywanym w `sessionStorage` i automatycznym dołączaniu go do żądań HTMX. Nacisk kładziony jest na prostotę i funkcjonalność wymaganą dla MVP, z podstawową responsywnością i standardowymi praktykami dostępności.

## 2. Lista widoków

---

**1. Widok: Landing Page** - **Ścieżka widoku:** `/` (lub inna główna ścieżka aplikacji) - **Główny cel:** Przedstawienie aplikacji "routr", zachęcenie do rejestracji lub logowania. Służy jako cel przekierowania z Globalnej Strony Zapasowej. - **Kluczowe informacje do wyświetlenia:** Nazwa aplikacji ("routr"), krótki opis funkcjonalności, przyciski "Zaloguj się" i "Zarejestruj się". - **Kluczowe komponenty widoku:** Prosta struktura HTML, Nagłówek/Hero section, Stopka. - **UX, dostępność i względy bezpieczeństwa:** Podstawowa responsywność. Semantyczny HTML. Brak specyficznych wymagań bezpieczeństwa.

---

**2. Widok: Strona Logowania** - **Ścieżka widoku:** `/login-page` - **Główny cel:** Umożliwienie zalogowania się zarejestrowanym użytkownikom. - **Kluczowe informacje do wyświetlenia:** Formularz z polami na E-mail i Hasło, Przycisk "Zaloguj", link do strony rejestracji, miejsce na komunikaty o błędach. - **Kluczowe komponenty widoku:** Formularz (Bootstrap), Pola Input (`type="email"`, `type="password"`), Przycisk (Bootstrap), Komponent Alert (Bootstrap) do wyświetlania błędów (`401 Unauthorized`, itp.), Kontener na formularz (np. Card Bootstrapa). HTMX do obsługi wysyłki formularza (`hx-post="/api/v1/auth/login"`) i obsługi odpowiedzi (przekierowanie lub błąd). - **UX, dostępność i względy bezpieczeństwa:** Jasne etykiety pól, obsługa błędów walidacji i uwierzytelniania. Atrybuty `required`. Podstawowa responsywność. Użycie `type="password"`.

---

**3. Widok: Strona Rejestracji** - **Ścieżka widoku:** `/register-page` - **Główny cel:** Umożliwienie rejestracji nowym użytkownikom. - **Kluczowe informacje do wyświetlenia:** Formularz z polami na E-mail i Hasło (potencjalnie Potwierdź Hasło), Przycisk "Zarejestruj", link do strony logowania, miejsce na komunikaty o błędach. - **Kluczowe komponenty widoku:** Formularz (Bootstrap), Pola Input, Przycisk (Bootstrap), Komponent Alert (Bootstrap) do wyświetlania błędów (np. zajęty email `409`, błędy walidacji `400`/`422`). HTMX do obsługi wysyłki formularza (`hx-post="/api/v1/auth/register"`) i obsługi odpowiedzi. - **UX, dostępność i względy bezpieczeństwa:** Jasne etykiety, obsługa błędów, wskazówki dotyczące wymagań hasła (jeśli są). Podstawowa responsywność. Użycie `type="password"`.

---

**4. Widok: Dashboard / Lista Linków** - **Ścieżka widoku:** `/links` - **Główny cel:** Wyświetlenie listy wszystkich linków routr utworzonych przez zalogowanego użytkownika. Umożliwienie nawigacji do edycji, inicjowanie usuwania i tworzenia nowych linków. Domyślny widok po zalogowaniu. - **Kluczowe informacje do wyświetlenia:** Tabela z linkami: Alias (link do edycji), Pełny URL (`routr.app/alias`), Całkowita liczba kliknięć (`total_clicks`). Przyciski akcji per wiersz: "Edytuj", "Usuń", "Kopiuj URL". Komponent paginacji (jeśli zaimplementowana). Przycisk "Utwórz nowy link" (w Navbarze). Komunikat o pustym stanie, jeśli brak linków. Miejsce na globalne alerty. - **Kluczowe komponenty widoku:** Nawigacja Górna (Navbar), Tabela (Bootstrap `table`, `table-hover`), Przyciski (Bootstrap, potencjalnie z ikonami), Komponent Paginacji (Bootstrap, prosty), Komponent Alert (Bootstrap), Logika HTMX do obsługi paginacji (`hx-get`), usuwania (`hx-delete` z potwierdzeniem, `hx-target="closest tr"`, `hx-swap="outerHTML"`), kopiowania URL (JS). - **UX, dostępność i względy bezpieczeństwa:** Czytelna prezentacja danych. Łatwy dostęp do akcji. Potwierdzenie przed usunięciem. Podstawowa responsywność tabeli. Semantyczna struktura tabeli (`thead`, `tbody`, `th scope="col"`). Odpowiednie atrybuty ARIA dla dynamicznych elementów.

---

**5. Widok: Tworzenie Linku** - **Ścieżka widoku:** `/links/new` - **Główny cel:** Umożliwienie użytkownikowi zdefiniowania aliasu i opcjonalnie domyślnego URL dla nowego linku routr. - **Kluczowe informacje do wyświetlenia:** Formularz z polem na Alias (wymagane, walidacja HTML5: `pattern`, `maxlength`), pole na Domyślny URL (opcjonalne, `type="url"`), Przycisk "Utwórz link". Miejsce na komunikaty o błędach (np. `409 Conflict` dla aliasu). - **Kluczowe komponenty widoku:** Nawigacja Górna (Navbar), Formularz (Bootstrap), Pola Input, Przycisk, Komponent Alert. Logika HTMX (`hx-post="/api/v1/links"`) do wysłania formularza. Serwer po sukcesie przekierowuje (odpowiedź HTTP 302/303 lub specjalny nagłówek HTMX `HX-Redirect`) do widoku edycji `/links/{new_id}/edit`. - **UX, dostępność i względy bezpieczeństwa:** Prosty, jednozadaniowy formularz. Jasna walidacja i obsługa błędów. Podstawowa responsywność.

---

**6. Widok: Edycja Linku** - **Ścieżka widoku:** `/links/{id}/edit` - **Główny cel:** Konfiguracja istniejącego linku: ustawienie domyślnego URL, zarządzanie regułami routingu, przeglądanie statystyk. - **Kluczowe informacje do wyświetlenia:** Alias linku (tylko do odczytu), Pole edycji dla Domyślnego URL (z przyciskiem zapisu/HTMX `hx-patch`). Zakładki (Tabs) przełączające widok między "Reguły" a "Statystyki". Miejsce na alerty dotyczące operacji na linku/regułach. - **Kluczowe komponenty widoku:** Nawigacja Górna (Navbar), Pole tekstowe (read-only), Formularz/Pole Input dla Default URL (Bootstrap), Komponent zakładek (Bootstrap Tabs), Komponent Alert (Bootstrap). - **UX, dostępność i względy bezpieczeństwa:** Czytelne rozdzielenie sekcji konfiguracyjnych. Łatwa nawigacja między regułami a statystykami. Podstawowa responsywność. Użycie ARIA dla zakładek.

    **6.a. Zakładka "Reguły" (w widoku Edycji Linku)**
        - **Główny cel:** Wyświetlenie listy reguł dla danego linku, umożliwienie ich edycji, usuwania oraz dodawania nowych.
        - **Kluczowe informacje do wyświetlenia:** Tabela z regułami: Priorytet, Typ (Czas/Kliknięcia), Cel (skrócony URL/ "HTML"), Stan/Limit (np. `15/100` kliknięć, zakres dat), Aktualne kliknięcia (`current_clicks`). Przyciski akcji per wiersz: "Edytuj", "Usuń". Przycisk "Dodaj regułę". Komunikat o pustym stanie.
        - **Kluczowe komponenty widoku:** Tabela (Bootstrap), Przyciski (Bootstrap). Logika HTMX do ładowania listy (`hx-get` przy aktywacji zakładki?), wywoływania modala edycji, inicjowania usuwania (`hx-delete` z potwierdzeniem).
        - **UX, dostępność i względy bezpieczeństwa:** Przejrzysta lista reguł, posortowana wg priorytetu. Łatwy dostęp do akcji. Potwierdzenie usunięcia. Semantyczna tabela.

    **6.b. Zakładka "Statystyki" (w widoku Edycji Linku)**
        - **Główny cel:** Wyświetlenie podstawowych statystyk kliknięć dla danego linku.
        - **Kluczowe informacje do wyświetlenia:** Całkowita liczba kliknięć linku (`total_clicks`). Tabela ze statystykami per cel/reguła: Typ Celu (URL/HTML), Wartość Celu (URL/ "HTML"), Liczba Kliknięć (`current_clicks`). Komunikat o braku statystyk.
        - **Kluczowe komponenty widoku:** Wyświetlanie tekstu, Tabela (Bootstrap). Logika HTMX do ładowania danych (`hx-get` przy aktywacji zakładki?).
        - **UX, dostępność i względy bezpieczeństwa:** Prosta i czytelna prezentacja danych MVP. Semantyczna tabela.

---

**7. Komponent: Modal Edytora Reguł** - **Ścieżka widoku:** N/A (Komponent modalny) - **Główny cel:** Zapewnienie interfejsu do tworzenia nowej lub edycji istniejącej reguły routingu. - **Kluczowe informacje do wyświetlenia:** Formularz zawierający: Priorytet (liczba, `min="1"`), Typ Reguły (select: Czas/Kliknięcia), Typ Celu (select: URL/HTML), Wartość Celu (input `type="url"` lub `textarea`), Maksymalna Liczba Kliknięć (input `type="number"`, `min="1"`, widoczne warunkowo), Czas Start/Koniec (inputy tekstowe z dołączonym Flatpickr, widoczne warunkowo, z etykietą "(UTC)"). Przyciski "Zapisz" i "Anuluj". Miejsce na komunikaty o błędach wewnątrz modala. - **Kluczowe komponenty widoku:** Komponent Modal (Bootstrap), Formularz (Bootstrap), Pola Input (różne typy), Select (Bootstrap), Textarea (Bootstrap), Integracja z Flatpickr (JS), Przyciski (Bootstrap), Komponent Alert (Bootstrap). Logika HTMX (`hx-post` lub `hx-patch` na przycisku "Zapisz") do wysłania danych. Po sukcesie, HTMX powinien zamknąć modal (np. przez odpowiedź serwera z nagłówkiem `HX-Trigger: closeModalEvent` lub JS) i odświeżyć listę reguł w tle (`hx-target` na tabelę reguł). - **UX, dostępność i względy bezpieczeństwa:** Czytelny formularz z warunkowo wyświetlanymi polami. Jasna walidacja i obsługa błędów (np. konflikt priorytetu `409`). Użycie ARIA dla modala i formularza. Ostrożność przy polu HTML (poleganie na backendowej sanityzacji).

---

**8. Widok: Globalna Strona Zapasowa (Fallback)** - **Ścieżka widoku:** N/A (Serwowana przez logikę przekierowania `GET /{alias_path:path}`) - **Główny cel:** Poinformowanie użytkownika końcowego, że kliknięty link jest nieaktywny lub kampania zakończona. Automatyczne przekierowanie po chwili. - **Kluczowe informacje do wyświetlenia:** Prosty komunikat (np. "Link nieaktywny..."), Nazwa/logo aplikacji "routr". - **Kluczowe komponenty widoku:** Minimalistyczna strona HTML. Skrypt JavaScript (`setTimeout`, `window.location.href`) realizujący przekierowanie na Landing Page (`/`) po kilku sekundach. - **UX, dostępność i względy bezpieczeństwa:** Jasny komunikat. Automatyczne przekierowanie może być mylące, ale jest zgodne z ustaleniami.

---

## 3. Mapa podróży użytkownika

**Kluczowy Przypadek Użycia: Rejestracja, Utworzenie Linku i Dodanie Reguły Czasowej**

1.  **Start:** Użytkownik trafia na **Landing Page (`/`)**.
2.  **Rejestracja:** Klika "Zarejestruj się", przechodzi do **Strony Rejestracji (`/register-page`)**. Wypełnia formularz (email, hasło), klika "Zarejestruj".
3.  **Logowanie:** Po pomyślnej rejestracji zostaje przekierowany na **Stronę Logowania (`/login-page`)**. Wpisuje dane, klika "Zaloguj".
4.  **Dashboard:** Po pomyślnym logowaniu zostaje przekierowany na **Dashboard / Listę Linków (`/links`)**. Widzi (pustą) listę swoich linków.
5.  **Inicjacja Tworzenia Linku:** Klika przycisk "Utwórz nowy link" w Navbarze.
6.  **Definicja Aliasu:** Przechodzi na stronę **Tworzenie Linku (`/links/new`)**. Wpisuje unikalny `alias` (np. "moja-pierwsza-kampania"), opcjonalnie `default_url`, klika "Utwórz link".
7.  **Widok Edycji:** Po pomyślnym utworzeniu linku zostaje przekierowany do **Widoku Edycji Linku (`/links/{id}/edit`)** dla nowo utworzonego linku. Domyślnie aktywna jest zakładka "Reguły".
8.  **Inicjacja Dodania Reguły:** Klika przycisk "Dodaj regułę" w zakładce "Reguły".
9.  **Konfiguracja Reguły:** Pojawia się **Modal Edytora Reguł**. Użytkownik:
    - Wpisuje `Priorytet` (np. 1).
    - Wybiera `Typ Reguły` = "Czas".
    - Wybiera `Typ Celu` = "URL".
    - Wkleja docelowy `URL` w polu "Wartość Celu".
    - Używa Flatpickr do wybrania `Czasu Start` i `Czasu Koniec` (pamiętając, że to UTC).
    - Klika "Zapisz".
10. **Zapis i Odświeżenie:** Modal zostaje zamknięty. Lista reguł w zakładce "Reguły" zostaje automatycznie odświeżona (przez HTMX), pokazując nowo dodaną regułę. Wyświetlony zostaje krótki komunikat o sukcesie.
11. **Kopiowanie Linku:** Użytkownik wraca na **Listę Linków (`/links`)** (klikając link w Navbarze). Znajduje swój link i klika przycisk "Kopiuj URL", aby skopiować `routr.app/moja-pierwsza-kampania` do schowka.

**Inne przepływy:** Edycja/Usuwanie linków i reguł, przeglądanie statystyk, wylogowanie - realizowane przez odpowiednie przyciski i nawigację w ramach opisanych widoków.

## 4. Układ i struktura nawigacji

**Układ Ogólny:**
Większość widoków dla zalogowanego użytkownika będzie korzystać ze wspólnego układu:

- **Górna Belka Nawigacyjna (Navbar):** Stała na górze strony.
- **Kontener Główny:** Poniżej Navbara, zawierający dynamiczną treść specyficzną dla danego widoku (np. tabela linków, formularz edycji z zakładkami).
- **Stopka (Opcjonalnie):** Prosta stopka na dole strony (może być pominięta w MVP).

**Nawigacja Główna (dla zalogowanego użytkownika):**
Realizowana przez **Navbar (Bootstrap)**, zawierający:

- **Logo/Nazwa "routr":** Po lewej stronie, linkuje do Dashboardu (`/links`).
- **Link "Moje Linki":** Linkuje do Dashboardu (`/links`).
- **Przycisk "Utwórz nowy link":** Linkuje do strony tworzenia linku (`/links/new`).
- **Przycisk/Link "Wyloguj":** Po prawej stronie. Kliknięcie inicjuje proces wylogowania (czyszczenie `sessionStorage`, przekierowanie na `/login-page`).

**Nawigacja Kontekstowa:**

- Przejście z listy linków do edycji: Kliknięcie aliasu lub przycisku "Edytuj" w wierszu tabeli.
- Przełączanie między Regułami a Statystykami: Kliknięcie odpowiedniej zakładki (Bootstrap Tabs) w widoku edycji linku.
- Otwieranie Modala Edytora Reguł: Kliknięcie przycisków "Dodaj regułę" lub "Edytuj" przy regule.

**Nawigacja Publiczna:**

- Proste linki między Landing Page (`/`), Stroną Logowania (`/login-page`) i Stroną Rejestracji (`/register-page`).

## 5. Kluczowe komponenty

Komponenty te będą reużywane w różnych widokach, zapewniając spójność UI:

- **Navbar (Bootstrap):** Główna nawigacja aplikacji dla zalogowanych użytkowników.
- **Formularze (Bootstrap):** Standardowe formularze do wprowadzania danych (logowanie, rejestracja, tworzenie linku, edycja default URL, edytor reguł). Wykorzystują HTMX do przesyłania danych.
- **Tabele (Bootstrap):** Do wyświetlania list danych (linki, reguły, statystyki). Z podstawową responsywnością.
- **Przyciski (Bootstrap):** Standardowe przyciski do wywoływania akcji (Zapisz, Usuń, Edytuj, Kopiuj, Dodaj, Zaloguj, Zarejestruj). Potencjalnie z ikonami.
- **Modale (Bootstrap):** Do wyświetlania formularza Edytora Reguł oraz ewentualnie do potwierdzania operacji usuwania.
- **Zakładki (Bootstrap Tabs):** Do rozdzielenia sekcji Reguły/Statystyki w widoku edycji linku.
- **Alerty (Bootstrap):** Do wyświetlania komunikatów zwrotnych (sukces, błąd) po operacjach HTMX.
- **Paginacja (Bootstrap):** Prosty komponent do nawigacji po stronach listy linków.
- **Flatpickr:** Biblioteka JS do wyboru daty i godziny w formularzu reguł.
- **Logika Kopiowania do Schowka:** Prosty fragment JavaScriptu obsługujący przycisk "Kopiuj URL".
