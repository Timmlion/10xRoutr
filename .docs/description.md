# Aplikacja – *routr* (MVP)

## Główny problem

Aplikacja *routr* rozwiązuje problem ograniczonego udostępniania treści w ramach kampanii marketingowych. Użytkownik może generować unikalne linki, które – na podstawie określonych zasad – przekierowują do wybranej lokalizacji lub wyświetlają niestandardową stronę HTML.

Zasady te są definiowane przez użytkownika. Mogą one obejmować m.in. liczbę kliknięć w link, datę czy rodzaj przeglądarki. Jeżeli żadna reguła nie zostanie spełniona, klient zostaje przekierowany na domyślną stronę informującą, że dany link jest już nieaktywny.

## Najmniejszy zestaw funkcjonalności

- **System autentykacji:**
  - Użytkownicy logują się przy użyciu rozwiązania BaaS (np. Supabase lub Pocketbase).

- **Zarządzanie linkami:**
  - Użytkownik może dodać nowy link, który zawiera:
    - Jeden lub wiele linków docelowych oraz zasady, na podstawie których klienci są przekierowywani.

- **Przekierowanie (redirect):**
  - Po wejściu na link aplikacja sprawdza, które warunki są spełnione, i na tej podstawie przekierowuje do odpowiedniej lokalizacji.

- **Edycja linków:**
  - Użytkownik ma możliwość zmiany linków docelowych oraz edycji ustawionych reguł dla już utworzonych linków.

- **Podstawowy podgląd statystyk:**
  - Dashboard zawiera podstawowe statystyki, takie jak liczba wejść na link pierwotny oraz liczba przekierowań dla każdego z celów.

## Co NIE wchodzi w zakres MVP

- **Zaawansowane mechanizmy routingu:**
  - Zamiast reverse proxy stosowany jest prosty mechanizm HTTP redirect.

- **Rozbudowana analityka i raportowanie:**
  - Szczegółowe statystyki (np. data ostatniego kliknięcia czy zaawansowana analiza ruchu) nie są implementowane. W MVP wystarczy jedynie liczba kliknięć.

- **Rozbudowany system zarządzania użytkownikami:**
  - Ograniczamy się do podstawowych funkcji autentykacji i zarządzania linkami, wykorzystując gotowe rozwiązania BaaS.

- **Funkcje premium i integracje:**
  - Funkcje premium, dynamiczne modyfikowanie treści końcowej na podstawie statystyk, dodatkowe opcje konfiguracyjne (np. warunki oparte na liczniku wejść lub rodzaju urządzenia), a także integracje z modułami społecznościowymi – zostają pominięte.

- **Dodatkowe zabezpieczenia:**
  - W MVP nie wprowadzamy dodatkowych mechanizmów zabezpieczających, takich jak ograniczenie częstotliwości modyfikacji linków czy rozbudowana walidacja adresów URL.

## Kryteria sukcesu

- **Stabilność działania:**
  - Aplikacja poprawnie autoryzuje użytkowników oraz umożliwia tworzenie i edycję linków.
  - Mechanizm przekierowania działa zgodnie z ustawionymi regułami – poprawnie sprawdzany jest warunek czasowy, a użytkownicy trafiają na odpowiednie strony (link docelowy lub strona informacyjna).

- **Pozytywny feedback od użytkowników:**
  - Użytkownicy zgłaszają minimalną liczbę błędów lub problemów podczas korzystania z MVP.
  - Opinie potwierdzają, że podstawowe funkcje (logowanie, zarządzanie linkami, przekierowania) są intuicyjne i działają zgodnie z oczekiwaniami.

- **KPI:**
  - Monitorowanie liczby utworzonych i aktywnych linków – celem jest osiągnięcie minimum 50 aktywnych linków w określonym czasie (np. w pierwszym miesiącu od wdrożenia).
  - Liczba przekierowań (kliknięć) jako wskaźnik stabilności działania mechanizmu oraz poziomu satysfakcji użytkowników.