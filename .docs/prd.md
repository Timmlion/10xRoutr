# Dokument wymagań produktu (PRD) - routr (MVP)

## 1. Przegląd produktu

Aplikacja *routr* (w wersji Minimum Viable Product - MVP) to narzędzie webowe zaprojektowane w celu rozwiązania problemu ograniczonego i statycznego udostępniania treści w kampaniach marketingowych. Umożliwia użytkownikom, głównie influencerom, generowanie unikalnych linków (np. `routr.app/moja-kampania`). Te linki, po kliknięciu przez użytkownika końcowego, inteligentnie przekierowują do różnych miejsc docelowych (innych adresów URL lub niestandardowych stron HTML) w oparciu o zestaw reguł zdefiniowanych przez twórcę linku.

W wersji MVP, reguły mogą opierać się na kryteriach czasowych (okres ważności) LUB ilościowych (liczba kliknięć). Każda reguła ma przypisany priorytet decydujący o kolejności jej sprawdzania. Złożone scenariusze (np. limit kliknięć obowiązujący tylko w określonym czasie) są realizowane poprzez kombinację wielu reguł z odpowiednimi priorytetami. Aplikacja udostępnia również podstawowe statystyki dotyczące liczby kliknięć w link główny oraz poszczególne cele przekierowań.

System opiera się na architekturze wykorzystującej Supabase jako Backend-as-a-Service (BaaS) do autentykacji i potencjalnie przechowywania danych (jak kod HTML), oraz prosty mechanizm przekierowań HTTP.

## 2. Problem użytkownika

Influencerzy i marketerzy często prowadzą kampanie, które wymagają bardziej dynamicznego zarządzania linkami niż oferują standardowe skracacze URL. Istnieje potrzeba łatwego kierowania ruchu na różne strony docelowe w zależności od czasu trwania promocji (np. oferta ważna tylko w weekend) lub jej popularności (np. specjalny link tylko dla pierwszych 100 osób). Obecne rozwiązania często nie oferują takiej elastyczności w prosty i zintegrowany sposób, zmuszając użytkowników do manualnych zmian lub stosowania skomplikowanych obejść. *routr* ma na celu uproszczenie tego procesu, dając użytkownikom kontrolę nad przepływem ruchu z ich linków marketingowych, umożliwiając tworzenie kombinacji reguł dla złożonych scenariuszy.

## 3. Wymagania funkcjonalne

### 3.1. Autentykacja (Auth)
*   FR-001: Użytkownicy muszą mieć możliwość rejestracji konta w systemie.
*   FR-002: Zarejestrowani użytkownicy muszą mieć możliwość logowania się do systemu.
*   FR-003: System wykorzystuje Supabase do obsługi procesów rejestracji i logowania.

### 3.2. Zarządzanie Linkami *routr* (Link Management)
*   FR-004: Zalogowany użytkownik może utworzyć nowy link *routr*.
*   FR-005: Podczas tworzenia linku, użytkownik musi zdefiniować unikalny alias (ścieżkę) dla linku, np. `moja-kampania`, który będzie częścią finalnego URL (`routr.app/moja-kampania`).
*   FR-006: Alias może zawierać wyłącznie małe litery, cyfry oraz myślniki (`-`).
*   FR-007: System musi walidować unikalność aliasu w całej aplikacji. W przypadku konfliktu, użytkownik otrzymuje stosowny komunikat błędu.
*   FR-008: Raz utworzony alias linku *routr* nie może być zmieniony.
*   FR-009: Zalogowany użytkownik może edytować konfigurację istniejącego linku *routr* (reguły, cele, domyślny URL), ale nie jego alias.
*   FR-010: Zalogowany użytkownik może przeglądać listę swoich utworzonych linków *routr*.

### 3.3. Zarządzanie Regułami (Rule Management)
*   FR-011: Do każdego linku *routr* użytkownik może dodać jedną lub więcej reguł przekierowania.
*   FR-012: Każda reguła musi mieć przypisany unikalny, numeryczny priorytet (liczba całkowita) w ramach danego linku *routr*. Niższa liczba oznacza wyższy priorytet.
*   FR-013: System (API/UI) musi walidować unikalność priorytetu podczas dodawania/edycji reguły. Użytkownik otrzymuje błąd przy próbie przypisania istniejącego priorytetu.
*   FR-013a: W wersji MVP, każda pojedyncza instancja reguły opiera się na jednym głównym typie warunku: Czas LUB Ilość Kliknięć.
*   FR-014: Użytkownik może zdefiniować regułę typu "Czas".
    *   FR-014.1: Reguła czasowa wymaga ustawienia daty i godziny początkowej oraz daty i godziny końcowej ważności.
    *   FR-014.2: Walidacja dat odbywa się po stronie serwera API. (Uwaga: Należy zdefiniować i konsekwentnie stosować strefę czasową, np. UTC).
*   FR-015: Użytkownik może zdefiniować regułę typu "Ilość Kliknięć".
    *   FR-015.1: Reguła ilościowa wymaga ustawienia maksymalnej liczby kliknięć (dodatnia liczba całkowita), po której reguła przestaje być aktywna.
*   FR-015a: Złożone scenariusze logiczne (np. 'pierwsze 100 kliknięć tylko w maju') są realizowane przez kombinację wielu reguł z różnymi typami warunków i odpowiednio ustawionymi priorytetami (patrz US-017).
*   FR-016: Użytkownik może edytować parametry istniejących reguł (typ, wartości, priorytet).
*   FR-017: Użytkownik może usuwać istniejące reguły.
*   FR-018: System jest zaprojektowany modularnie, aby umożliwić dodawanie nowych typów reguł w przyszłości (oraz potencjalnie łączenie warunków w jednej regule w przyszłych wersjach).

### 3.4. Definiowanie Celów Przekierowań (Target Definition)
*   FR-019: Każda zdefiniowana reguła musi wskazywać na jeden cel przekierowania.
*   FR-020: Celem przekierowania może być:
    *   FR-020.1: Zewnętrzny adres URL (musi być poprawnym adresem HTTP/HTTPS, podstawowa walidacja formatu i długości).
    *   FR-020.2: Niestandardowa strona HTML (użytkownik wkleja kod HTML, potencjalnie z CSS/JS, do pola tekstowego; kod przechowywany w Supabase).
*   FR-021: Dla niestandardowej strony HTML obowiązuje limit długości wpisanego kodu. (Uwaga: Należy zdefiniować limit i podstawowe mechanizmy sanityzacji/walidacji HTML).
*   FR-022: Użytkownik może edytować cel przypisany do reguły.

### 3.5. Domyślne Przekierowanie (Default Redirect)
*   FR-023: Użytkownik może opcjonalnie zdefiniować domyślny adres URL przekierowania dla całego linku *routr*.
*   FR-024: Ten domyślny URL jest używany, gdy użytkownik końcowy kliknie link *routr*, ale żadna z aktywnych reguł nie zostanie spełniona.

### 3.6. Mechanizm Przekierowania (Redirection Engine)
*   FR-025: Dostęp do linku `routr.app/alias` inicjuje proces przekierowania.
*   FR-026: System pobiera wszystkie aktywne reguły powiązane z danym aliasem, posortowane według priorytetu (od najniższej liczby).
*   FR-027: System sprawdza kolejno warunki zdefiniowane dla każdej reguły, zgodnie z jej typem (Czas lub Ilość Kliknięć).
*   FR-028: Jeśli warunek reguły czasowej jest spełniony (aktualny czas mieści się w zdefiniowanym przedziale), reguła jest uznawana za pasującą.
*   FR-029: Jeśli warunek reguły ilościowej jest spełniony (aktualna liczba kliknięć dla tej reguły jest mniejsza niż zdefiniowany limit), reguła jest uznawana za pasującą.
*   FR-030: Pierwsza napotkana pasująca reguła (zgodnie z priorytetem) determinuje cel przekierowania.
*   FR-031: Jeśli celem jest URL, system wykonuje przekierowanie HTTP (np. 302 Found) na ten adres.
*   FR-032: Jeśli celem jest HTML, system serwuje zapisaną zawartość HTML użytkownikowi końcowemu (status HTTP 200 OK).
*   FR-033: Jeśli żadna z reguł nie zostanie spełniona, system sprawdza, czy zdefiniowano domyślny URL (FR-023). Jeśli tak, wykonuje przekierowanie HTTP na ten adres.
*   FR-034: Jeśli żadna reguła nie pasuje i nie zdefiniowano domyślnego URL, system przekierowuje na globalną, standardową stronę informacyjną aplikacji (np. informującą, że link jest nieaktywny lub kampania zakończona). (Uwaga: Treść i wygląd tej strony wymagają zdefiniowania).
*   FR-035: Każde kliknięcie w link *routr* jest zliczane.
*   FR-036: Każde udane przekierowanie (lub wyświetlenie HTML) wynikające z dopasowania konkretnej reguły jest zliczane dla tej konkretnej reguły/celu.

### 3.7. Statystyki (Statistics)
*   FR-037: Zalogowany użytkownik ma dostęp do prostego dashboardu ze statystykami dla swoich linków *routr*.
*   FR-038: Dla każdego linku *routr* wyświetlana jest całkowita liczba kliknięć w ten link.
*   FR-039: Dla każdego celu (URL lub HTML) powiązanego z regułami danego linku *routr*, wyświetlana jest liczba przekierowań/wyświetleń na ten konkretny cel.
*   FR-040: Statystyki nie są resetowane podczas edycji reguł lub celów.
*   FR-041: MVP nie obejmuje zaawansowanych statystyk (np. unikalni użytkownicy, dane czasowe kliknięć, geolokalizacja).

### 3.8. Wymagania Niefunkcjonalne (MVP)
*   FR-042: Aplikacja powinna być dostępna i responsywna (brak konkretnych SLA dla MVP).
*   FR-043: Przekierowanie powinno następować możliwie szybko (brak ścisłych wymagań czasowych dla MVP, ale unikać zauważalnych opóźnień).
*   FR-044: Podstawowe zabezpieczenia przed powszechnymi atakami webowymi (np. XSS, CSRF) w interfejsie użytkownika (panel administracyjny).

## 4. Granice produktu

Następujące funkcje i cechy są świadomie wyłączone z zakresu MVP:

*   Łączenie wielu typów warunków (np. Czas ORAZ Ilość) w ramach jednej instancji reguły. Złożone scenariusze są realizowane przez kombinację wielu reguł.
*   Zaawansowane typy reguł (np. geolokalizacja, typ urządzenia, język przeglądarki).
*   Zaawansowane mechanizmy routingu (np. reverse proxy, modyfikacja nagłówków).
*   Rozbudowana analityka i raportowanie (np. wykresy czasowe, mapy kliknięć, analiza źródeł ruchu, eksport danych).
*   Rozbudowane zarządzanie użytkownikami (role, uprawnienia, zespoły).
*   Funkcje premium (np. własne domeny, A/B testy).
*   Integracje z zewnętrznymi systemami (np. platformy społecznościowe, narzędzia analityczne).
*   Dynamiczne modyfikowanie treści strony docelowej na podstawie statystyk lub parametrów.
*   Zaawansowane zabezpieczenia (np. ochrona przed zaawansowanymi botami, rate limiting, kompleksowa walidacja URL).
*   Mechanizmy cache'owania w celu optymalizacji wydajności przekierowań.
*   Zarządzanie cyklem życia linków (archiwizacja, oznaczanie wygasłych linków).
*   Możliwość edycji aliasu linku *routr* po jego utworzeniu.
*   Zaawansowany edytor HTML/CSS/JS.

## 5. Historyjki użytkowników

### 5.1. Autentykacja

#### US-001: Rejestracja nowego użytkownika
*   ID: US-001
*   Tytuł: Rejestracja konta
*   Opis: Jako nowy użytkownik, chcę móc zarejestrować konto w aplikacji *routr* używając adresu e-mail i hasła, abym mógł zacząć tworzyć i zarządzać linkami.
*   Kryteria akceptacji:
    *   Istnieje formularz rejestracji z polami na e-mail i hasło.
    *   Po poprawnym wypełnieniu i wysłaniu formularza, konto użytkownika jest tworzone w Supabase.
    *   Użytkownik otrzymuje potwierdzenie pomyślnej rejestracji (np. zostaje automatycznie zalogowany lub widzi komunikat).
    *   W przypadku błędów (np. zajęty e-mail, nieprawidłowe hasło) użytkownik widzi stosowny komunikat.

#### US-002: Logowanie użytkownika
*   ID: US-002
*   Tytuł: Logowanie do aplikacji
*   Opis: Jako zarejestrowany użytkownik, chcę móc zalogować się do aplikacji *routr* używając mojego adresu e-mail i hasła, abym uzyskał dostęp do panelu zarządzania linkami.
*   Kryteria akceptacji:
    *   Istnieje formularz logowania z polami na e-mail i hasło.
    *   Po podaniu poprawnych danych uwierzytelniających, użytkownik zostaje zalogowany i przekierowany do panelu (dashboardu).
    *   W przypadku podania niepoprawnych danych, użytkownik widzi stosowny komunikat błędu.
    *   Sesja użytkownika jest utrzymywana po zalogowaniu.

### 5.2. Zarządzanie Linkami *routr*

#### US-003: Tworzenie nowego linku *routr*
*   ID: US-003
*   Tytuł: Tworzenie linku *routr*
*   Opis: Jako zalogowany użytkownik (influencer), chcę móc utworzyć nowy link *routr* podając unikalny alias, abym mógł rozpocząć konfigurację przekierowań dla mojej kampanii.
*   Kryteria akceptacji:
    *   W panelu istnieje opcja (np. przycisk) rozpoczęcia tworzenia nowego linku.
    *   Wyświetla się formularz wymagający podania aliasu linku.
    *   Pole aliasu akceptuje tylko małe litery, cyfry i myślniki.
    *   System sprawdza unikalność aliasu przed zapisaniem.
    *   Po pomyślnym utworzeniu, użytkownik jest przekierowywany do widoku edycji/konfiguracji tego linku lub widzi go na liście swoich linków.
    *   Nowo utworzony link ma format `routr.app/podany-alias`.

#### US-004: Obsługa konfliktu aliasu
*   ID: US-004
*   Tytuł: Konflikt nazwy aliasu
*   Opis: Jako zalogowany użytkownik, próbując utworzyć link *routr* z aliasem, który już istnieje, chcę zobaczyć jasny komunikat błędu informujący o konflikcie, abym mógł wybrać inną nazwę.
*   Kryteria akceptacji:
    *   Gdy użytkownik próbuje zapisać nowy link z aliasem, który jest już używany przez inny link w systemie, zapis jest blokowany.
    *   Użytkownikowi wyświetlany jest czytelny komunikat błędu, np. "Ten alias jest już zajęty. Wybierz inny."
    *   Formularz pozostaje wypełniony (z wyjątkiem pola aliasu lub z możliwością jego edycji), aby użytkownik mógł łatwo poprawić nazwę.

#### US-005: Wyświetlanie listy linków
*   ID: US-005
*   Tytuł: Lista moich linków *routr*
*   Opis: Jako zalogowany użytkownik, chcę widzieć listę wszystkich utworzonych przeze mnie linków *routr* w moim panelu, abym mógł łatwo nimi zarządzać i sprawdzać ich status.
*   Kryteria akceptacji:
    *   W panelu użytkownika (dashboard) dostępna jest sekcja wyświetlająca listę linków.
    *   Lista zawiera co najmniej alias (lub pełny URL) każdego linku.
    *   Z listy możliwe jest przejście do widoku edycji/statystyk danego linku.

### 5.3. Konfiguracja Reguł i Celów

#### US-006: Dodawanie reguły czasowej
*   ID: US-006
*   Tytuł: Dodawanie reguły czasowej
*   Opis: Jako zalogowany użytkownik, podczas konfiguracji linku *routr*, chcę móc dodać regułę opartą na czasie, określając datę/godzinę początkową i końcową, oraz przypisać jej cel (URL lub HTML) i unikalny priorytet, abym mógł kierować ruch tylko w określonym okresie.
*   Kryteria akceptacji:
    *   W formularzu edycji linku istnieje opcja dodania nowej reguły.
    *   Można wybrać typ reguły "Czas".
    *   Dostępne są pola do wyboru daty i godziny początkowej oraz końcowej (np. za pomocą date/time pickerów).
    *   Można zdefiniować cel przekierowania (URL lub HTML) dla tej reguły.
    *   Można wprowadzić unikalny numeryczny priorytet dla tej reguły.
    *   Po zapisaniu, nowa reguła jest widoczna na liście reguł dla danego linku *routr*.

#### US-007: Dodawanie reguły ilościowej
*   ID: US-007
*   Tytuł: Dodawanie reguły ilości kliknięć
*   Opis: Jako zalogowany użytkownik, podczas konfiguracji linku *routr*, chcę móc dodać regułę opartą na liczbie kliknięć, określając maksymalną liczbę, oraz przypisać jej cel (URL lub HTML) i unikalny priorytet, abym mógł ograniczyć dostęp do specjalnej oferty.
*   Kryteria akceptacji:
    *   W formularzu edycji linku istnieje opcja dodania nowej reguły.
    *   Można wybrać typ reguły "Ilość Kliknięć".
    *   Dostępne jest pole do wprowadzenia maksymalnej liczby kliknięć (dodatnia liczba całkowita).
    *   Można zdefiniować cel przekierowania (URL lub HTML) dla tej reguły.
    *   Można wprowadzić unikalny numeryczny priorytet dla tej reguły.
    *   Po zapisaniu, nowa reguła jest widoczna na liście reguł dla danego linku *routr*.

#### US-008: Ustawianie celu jako URL
*   ID: US-008
*   Tytuł: Cel reguły jako URL
*   Opis: Jako zalogowany użytkownik, konfigurując regułę, chcę móc ustawić jako jej cel zewnętrzny adres URL, abym mógł przekierować użytkowników na inną stronę internetową.
*   Kryteria akceptacji:
    *   W formularzu definicji reguły można wybrać opcję celu "URL".
    *   Dostępne jest pole tekstowe do wprowadzenia adresu URL.
    *   System wykonuje podstawową walidację formatu URL (np. sprawdza obecność `http://` lub `https://`) i maksymalnej długości.
    *   Zapisany URL jest powiązany z daną regułą.

#### US-009: Ustawianie celu jako HTML
*   ID: US-009
*   Tytuł: Cel reguły jako niestandardowy HTML
*   Opis: Jako zalogowany użytkownik, konfigurując regułę, chcę móc wkleić własny kod HTML (potencjalnie z CSS/JS) jako jej cel, abym mógł wyświetlić użytkownikom niestandardową treść bezpośrednio.
*   Kryteria akceptacji:
    *   W formularzu definicji reguły można wybrać opcję celu "HTML".
    *   Dostępne jest pole tekstowe (textarea) do wklejenia kodu HTML.
    *   Obowiązuje limit znaków dla wprowadzanego kodu.
    *   System zapisuje wprowadzony kod HTML w Supabase, powiązany z daną regułą.
    *   W przypadku przekroczenia limitu znaków lub innych błędów zapisu, użytkownik widzi komunikat.

#### US-010: Zarządzanie priorytetami reguł
*   ID: US-010
*   Tytuł: Ustawianie i walidacja priorytetów reguł
*   Opis: Jako zalogowany użytkownik, zarządzając regułami dla linku *routr*, chcę móc przypisać każdej regule unikalny numer priorytetu, a system powinien uniemożliwić przypisanie tego samego priorytetu dwóm regułom, abym miał pewność co do kolejności ich sprawdzania.
*   Kryteria akceptacji:
    *   Każda reguła na liście ma pole do wprowadzenia/edycji jej priorytetu (liczba całkowita).
    *   Przy próbie zapisania zmian, system waliduje, czy wszystkie priorytety w ramach danego linku *routr* są unikalne.
    *   Jeśli występuje duplikat priorytetu, zapis jest blokowany, a użytkownik widzi komunikat błędu wskazujący problem.
    *   Lista reguł w interfejsie użytkownika jest sortowana według priorytetu (od najniższego numeru).

#### US-011: Edycja istniejącej reguły/celu
*   ID: US-011
*   Tytuł: Edycja reguły lub celu
*   Opis: Jako zalogowany użytkownik, chcę móc edytować parametry istniejącej reguły (np. zmienić datę końcową, limit kliknięć, priorytet) lub jej cel (zmienić URL, edytować HTML), abym mógł dostosować działanie linku *routr* bez tworzenia go od nowa.
*   Kryteria akceptacji:
    *   Na liście reguł dla linku *routr* istnieje opcja edycji każdej reguły.
    *   Formularz edycji pozwala na zmianę typu reguły, jej parametrów (daty, liczby kliknięć), priorytetu oraz celu (URL/HTML).
    *   Wszystkie walidacje (unikalność priorytetu, format URL, limit HTML) działają również podczas edycji.
    *   Zapisanie zmian aktualizuje konfigurację reguły. Edycja nie wpływa na zgromadzone statystyki.

#### US-012: Definiowanie domyślnego przekierowania
*   ID: US-012
*   Tytuł: Definiowanie domyślnego URL
*   Opis: Jako zalogowany użytkownik, konfigurując link *routr*, chcę móc opcjonalnie zdefiniować domyślny adres URL, na który użytkownicy będą przekierowani, jeśli żadna z moich reguł nie zostanie spełniona, abym uniknął wyświetlania im standardowej strony systemowej.
*   Kryteria akceptacji:
    *   W ustawieniach linku *routr* istnieje pole do wprowadzenia opcjonalnego domyślnego adresu URL.
    *   Pole akceptuje poprawny adres URL (walidacja jak dla celu URL).
    *   Zapisany URL jest używany przez mechanizm przekierowania (FR-033), gdy żadna reguła nie pasuje.
    *   Jeśli pole pozostanie puste, używana jest globalna strona systemowa (FR-034).

#### US-017: Tworzenie złożonego scenariusza za pomocą wielu reguł
*   ID: US-017
*   Tytuł: Konfiguracja kampanii "pierwsze 100 w maju, kolejne 100 w maju, reszta po maju"
*   Opis: Jako zalogowany użytkownik (influencer), chcę skonfigurować link *routr* tak, aby w maju pierwsze 100 kliknięć kierowało na stronę A, kolejne 100 kliknięć (od 101 do 200) w maju kierowało na stronę B, a wszystkie kliknięcia po maju (lub powyżej 200 w maju) kierowały na stronę C, wykorzystując kombinację reguł czasowych, ilościowych i priorytetów.
*   Kryteria akceptacji:
    *   Użytkownik może utworzyć Regułę 1: Typ=Ilość, Limit=100, Cel=Strona A, Priorytet=1.
    *   Użytkownik może utworzyć Regułę 2: Typ=Ilość, Limit=200, Cel=Strona B, Priorytet=2.
    *   Użytkownik może utworzyć Regułę 3: Typ=Czas, Start=1 Maja 00:00, Koniec=1 Czerwca 00:00, Cel=Strona C (lub Domyślny URL), Priorytet=3. (Ta reguła złapie kliknięcia >200 w maju).
    *   Użytkownik może utworzyć Regułę 4: Typ=Czas, Start=1 Czerwca 00:00, Koniec=(brak lub daleko w przyszłość), Cel=Strona C, Priorytet=4. (Ta reguła złapie kliknięcia po maju).
    *   (Alternatywnie do R3 i R4, można ustawić Stronę C jako domyślny URL dla całego linku *routr*).
    *   Mechanizm przekierowania poprawnie interpretuje priorytety i warunki tych reguł, kierując ruch zgodnie z opisanym scenariuszem.

### 5.4. Przekierowanie (Perspektywa Użytkownika Końcowego)

#### US-013: Pomyślne przekierowanie (Reguła Pasuje)
*   ID: US-013
*   Tytuł: Dostęp do linku *routr* - reguła pasuje
*   Opis: Jako użytkownik końcowy, klikając w link *routr* (np. `routr.app/promocja-czasowa`), chcę zostać przekierowany na odpowiednią stronę docelową (URL) lub zobaczyć niestandardową treść (HTML), jeśli spełniam warunki pierwszej pasującej reguły (np. klikam w okresie ważności reguły czasowej o najwyższym priorytecie).
*   Kryteria akceptacji:
    *   Gdy użytkownik wchodzi na URL linku *routr*.
    *   System poprawnie identyfikuje pierwszą pasującą regułę zgodnie z jej typem (czas/ilość) i priorytetem.
    *   Jeśli celem jest URL, następuje przekierowanie HTTP na ten URL.
    *   Jeśli celem jest HTML, użytkownikowi wyświetlana jest ta zawartość HTML.
    *   Odpowiednie liczniki kliknięć (ogólny i dla celu) są inkrementowane.

#### US-014: Przekierowanie domyślne (Brak Pasującej Reguły, Ustawiony Default)
*   ID: US-014
*   Tytuł: Dostęp do linku *routr* - brak pasującej reguły, jest default
*   Opis: Jako użytkownik końcowy, klikając w link *routr*, gdy żadna z aktywnych reguł nie jest spełniona (np. promocja czasowa wygasła, limit kliknięć osiągnięty), ale twórca linku zdefiniował domyślny URL, chcę zostać przekierowany na ten domyślny adres.
*   Kryteria akceptacji:
    *   Gdy użytkownik wchodzi na URL linku *routr*.
    *   System stwierdza, że żadna reguła nie pasuje.
    *   System identyfikuje, że zdefiniowano domyślny URL dla tego linku *routr*.
    *   Następuje przekierowanie HTTP na zdefiniowany domyślny URL.
    *   Licznik ogólny kliknięć jest inkrementowany.

#### US-015: Przekierowanie na stronę globalną (Brak Pasującej Reguły, Brak Default)
*   ID: US-015
*   Tytuł: Dostęp do linku *routr* - brak pasującej reguły, brak default
*   Opis: Jako użytkownik końcowy, klikając w link *routr*, gdy żadna z aktywnych reguł nie jest spełniona i twórca linku NIE zdefiniował domyślnego URL, chcę zostać przekierowany na standardową stronę informacyjną aplikacji *routr*, która poinformuje mnie, że link jest nieaktywny lub kampania zakończona.
*   Kryteria akceptacji:
    *   Gdy użytkownik wchodzi na URL linku *routr*.
    *   System stwierdza, że żadna reguła nie pasuje.
    *   System stwierdza, że NIE zdefiniowano domyślnego URL dla tego linku *routr*.
    *   Następuje przekierowanie HTTP na globalną stronę informacyjną aplikacji.
    *   Licznik ogólny kliknięć jest inkrementowany.

### 5.5. Statystyki

#### US-016: Przeglądanie statystyk linku
*   ID: US-016
*   Tytuł: Podgląd statystyk linku *routr*
*   Opis: Jako zalogowany użytkownik (influencer), chcę móc zobaczyć podstawowe statystyki dla wybranego linku *routr* w moim panelu, w tym całkowitą liczbę kliknięć oraz liczbę przekierowań na każdy zdefiniowany cel, abym mógł ocenić skuteczność mojej kampanii.
*   Kryteria akceptacji:
    *   W panelu użytkownika, dla każdego linku *routr* lub w jego widoku szczegółowym/edycji, dostępna jest sekcja statystyk.
    *   Wyświetlana jest całkowita liczba kliknięć zarejestrowanych dla danego linku *routr* (aliasu).
    *   Dla każdego celu (URL lub identyfikator strony HTML) powiązanego z regułami tego linku, wyświetlana jest liczba przekierowań/wyświetleń na ten konkretny cel.
    *   Statystyki są aktualizowane w rozsądnym czasie (niekoniecznie w czasie rzeczywistym dla MVP).

## 6. Metryki sukcesu

Sukces MVP aplikacji *routr* będzie mierzony na podstawie następujących kryteriów:

### 6.1. Stabilność i Funkcjonalność Podstawowa
*   Metryka: Poprawność działania kluczowych funkcji.
*   Sposób pomiaru:
    *   Testy funkcjonalne potwierdzające poprawną autentykację (rejestracja, logowanie).
    *   Testy potwierdzające możliwość tworzenia i edycji linków *routr* z regułami czasowymi i ilościowymi oraz celami URL/HTML.
    *   Testy mechanizmu przekierowania w różnych scenariuszach (pasująca reguła czasowa, pasująca reguła ilościowa, brak pasującej reguły z/bez domyślnego URL), weryfikujące kierowanie na właściwy cel. Testy złożonych scenariuszy z wieloma regułami (jak w US-017).
    *   Poprawność zliczania kliknięć (ogólnych i per cel).
*   Cel: Wysoka (>95%) skuteczność w testach kluczowych przepływów. Minimalna liczba krytycznych błędów zgłaszanych po wdrożeniu.

### 6.2. Pozytywny Feedback Użytkowników
*   Metryka: Satysfakcja użytkowników z podstawowej funkcjonalności.
*   Sposób pomiaru:
    *   Monitorowanie liczby i rodzaju zgłoszeń błędów oraz problemów z użytecznością przez pierwszych użytkowników (influencerów).
    *   Zbieranie bezpośrednich opinii (np. przez krótkie ankiety, wywiady) dotyczących intuicyjności interfejsu i spełnienia oczekiwań co do podstawowych funkcji (logowanie, tworzenie/edycja linków, działanie przekierowań, możliwość realizacji złożonych scenariuszy).
*   Cel: Niski (<5 na użytkownika w pierwszym miesiącu) wskaźnik zgłaszanych problemów. Dominacja pozytywnych opinii potwierdzających łatwość użycia i działanie zgodne z opisem.

### 6.3. Kluczowe Wskaźniki Efektywności (KPI)
*   Metryka 1: Adopcja platformy.
*   Sposób pomiaru: Liczba aktywnych linków *routr* utworzonych przez użytkowników. "Aktywny link" dla MVP definiowany jest jako każdy link utworzony w systemie.
*   Cel 1: Osiągnięcie minimum 50 aktywnych linków *routr* w ciągu pierwszego miesiąca od publicznego uruchomienia MVP.
*   Metryka 2: Użycie i stabilność mechanizmu przekierowań.
*   Sposób pomiaru: Łączna liczba zarejestrowanych przekierowań (kliknięć we wszystkie linki *routr*).
*   Cel 2: Ciągły wzrost liczby przekierowań, monitorowany jako wskaźnik wykorzystania platformy i pośrednio jej stabilności (brak masowych błędów w przekierowaniach).