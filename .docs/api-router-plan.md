# Plan Punktu Końcowego Przekierowania - routr (MVP)

Ten dokument opisuje projekt i działanie publicznego punktu końcowego przekierowania (`/{alias_path:path}`), który jest kluczową funkcjonalnością aplikacji _routr_. Jest on odpowiedzialny za przyjmowanie żądań na unikalne aliasy i kierowanie użytkowników końcowych do odpowiednich miejsc docelowych na podstawie zdefiniowanych reguł.

## 1. Zasób

- **Punkt Końcowy Przekierowania:** Główna, publicznie dostępna ścieżka aplikacji, która obsługuje dynamiczne przekierowania. Nie jest to typowy zasób RESTful CRUD, lecz punkt wejścia do logiki routingu.

## 2. Punkt końcowy

---

### 2.1. Publiczne Przekierowanie (`/{alias_path:path}`)

#### **Przekieruj na podstawie Aliasu**

- **Metoda:** `GET`
- **Ścieżka:** `/{alias_path:path}`
  - _Wyjaśnienie:_ Użycie `:path` w FastAPI pozwala przechwycić całą ścieżkę po głównym adresie URL aplikacji jako pojedynczy parametr `alias_path`. Zakładamy, że aplikacja jest hostowana tak, że `routr.app/` mapuje się na ten endpoint.
- **Opis:** Obsługuje przychodzące żądanie GET na unikalny alias linku. Wyszukuje odpowiedni link i jego reguły w bazie danych, ewaluuje reguły zgodnie z priorytetem i warunkami (czas lub liczba kliknięć), a następnie wykonuje przekierowanie HTTP do docelowego adresu URL, serwuje niestandardową zawartość HTML lub przekierowuje do domyślnego/globalnego URL zapasowego. Jednocześnie atomowo inkrementuje odpowiednie liczniki kliknięć.
- **Uwierzytelnianie:** **Niewymagane** (Endpoint jest publiczny).
- **Parametry ścieżki:**
  - `alias_path`: `string` (wymagany) - Unikalny alias linku routr (np. "moja-kampania" z adresu `routr.app/moja-kampania`).
- **Odpowiedź (Sukces - zależy od logiki):**
  - **Przekierowanie URL:**
    - **Kod:** `302 Found` (lub `307 Temporary Redirect` - do ustalenia, 302 jest powszechnym wyborem dla dynamicznych przekierowań)
    - **Nagłówki:** `Location: <docelowy_url>` (gdzie `<docelowy_url>` to `target_value` pasującej reguły lub `default_url` linku)
    - **Ciało:** Puste.
  - **Serwowanie HTML:**
    - **Kod:** `200 OK`
    - **Nagłówki:** `Content-Type: text/html; charset=utf-8`
    - **Ciało:** Zawartość `target_value` (kod HTML) pasującej reguły.
  - **Przekierowanie Globalne:**
    - **Kod:** `302 Found` (lub inny odpowiedni kod przekierowania)
    - **Nagłówki:** `Location: <url_strony_globalnej>` (gdzie `<url_strony_globalnej>` to predefiniowany URL dla nieaktywnych/nieznalezionych linków bez własnego domyślnego URL)
    - **Ciało:** Puste.
- **Kody błędów:**
  - `404 Not Found`: Link o podanym `alias_path` nie istnieje w bazie danych (`routr_links`).
  - `500 Internal Server Error`: Błąd podczas dostępu do bazy danych, ewaluacji reguł, inkrementacji liczników lub inny nieoczekiwany błąd serwera.

---

## 3. Uwierzytelnianie i autoryzacja

- **Uwierzytelnianie:** Ten punkt końcowy jest **publiczny** i nie wymaga uwierzytelniania użytkownika końcowego.
- **Autoryzacja (Dostęp Backendu do Bazy Danych):** Logika backendu obsługująca ten endpoint **musi** używać klucza `service_role` Supabase do wykonywania zapytań `SELECT` do tabel `routr_links` i `routing_rules` oraz operacji `UPDATE` do inkrementacji liczników. Jest to konieczne, aby ominąć polityki RLS (Row Level Security) skonfigurowane dla uwierzytelnionych użytkowników zarządzających linkami.

## 4. Walidacja i logika biznesowa

- **Walidacja Danych Wejściowych:**
  - Główną walidacją jest sprawdzenie, czy `alias_path` (otrzymany z URL) istnieje jako unikalny `alias` w tabeli `routr_links`. Jeśli nie, zwracany jest błąd `404 Not Found`.
  - Walidacja formatu samego aliasu (tylko dozwolone znaki) jest zapewniona przez ograniczenie `CHECK` w bazie danych przy tworzeniu linku.
- **Logika Biznesowa (Przepływ Przekierowania):**
  1.  **Wyszukanie Linku:** Znajdź rekord w `routr_links` na podstawie `alias_path` (korzystając z indeksu `idx_routr_links_alias`). Jeśli nie znaleziono, zwróć `404`.
  2.  **Inkrementacja Licznika Ogólnego:** **Atomowo** zaktualizuj licznik `total_clicks` dla znalezionego rekordu `routr_links` (`UPDATE routr_links SET total_clicks = total_clicks + 1 WHERE id = ...`). Obsłuż potencjalne błędy tej operacji.
  3.  **Pobranie Reguł:** Pobierz wszystkie powiązane rekordy z `routing_rules`, gdzie `link_id` pasuje do znalezionego linku, posortowane rosnąco według `priority` (korzystając z indeksu `idx_routing_rules_link_id_priority`).
  4.  **Ewaluacja Reguł:** Przetwarzaj pobrane reguły w pętli, zgodnie z ich priorytetem:
      - **Dla reguły typu 'time':** Sprawdź, czy aktualny czas serwera (w UTC) znajduje się pomiędzy `start_time` a `end_time` reguły.
      - **Dla reguły typu 'clicks':** Sprawdź, czy `current_clicks` reguły jest mniejsze niż `max_clicks`.
      - **Pierwsze Dopasowanie:** Jeśli warunek reguły jest spełniony, przejdź do kroku 5.
  5.  **Obsługa Dopasowanej Reguły:**
      - **Inkrementacja Licznika Reguły:** **Atomowo** zaktualizuj licznik `current_clicks` dla _dopasowanej_ reguły (`UPDATE routing_rules SET current_clicks = current_clicks + 1 WHERE id = ...`). Obsłuż potencjalne błędy.
      - **Sprawdź Typ Celu:**
        - Jeśli `target_type` to 'url', przygotuj odpowiedź HTTP z kodem `302 Found` (lub 307) i nagłówkiem `Location` ustawionym na `target_value`. Zakończ przetwarzanie.
        - Jeśli `target_type` to 'html', przygotuj odpowiedź HTTP z kodem `200 OK`, nagłówkiem `Content-Type: text/html; charset=utf-8` i ciałem zawierającym `target_value`. Zakończ przetwarzanie.
  6.  **Brak Dopasowania Reguł:** Jeśli pętla ewaluacji zakończy się bez znalezienia pasującej reguły:
      - Sprawdź, czy `default_url` w rekordzie `routr_links` jest ustawiony (nie jest NULL).
      - Jeśli tak, przygotuj odpowiedź HTTP z kodem `302 Found` (lub 307) i nagłówkiem `Location` ustawionym na `default_url`. Zakończ przetwarzanie.
      - Jeśli nie, przygotuj odpowiedź HTTP przekierowującą na predefiniowany, globalny URL strony informującej o nieaktywnym linku (np. `302 Found` z `Location: <global_fallback_url>`). Zakończ przetwarzanie.
  7.  **Obsługa Błędów:** W każdym kroku należy odpowiednio obsługiwać potencjalne błędy (np. błędy bazy danych) i zwracać kod `500 Internal Server Error`.
- **Kluczowe Aspekty Implementacji:**
  - **Atomowość liczników:** Niezbędne jest użycie atomowych operacji UPDATE w bazie danych, aby uniknąć problemów współbieżności przy zliczaniu kliknięć.
  - **Wydajność zapytań:** Wykorzystanie indeksów na `alias` i `(link_id, priority)` jest kluczowe dla szybkiego działania przekierowania.
  - **Bezpieczeństwo dostępu do DB:** Użycie klucza `service_role` dla wszystkich operacji DB w tym endpoincie.
