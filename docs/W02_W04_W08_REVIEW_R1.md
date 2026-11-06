# ETA FULL BSD — W02/W04: rozstrzygający przegląd W08 (R1)

Data: 2026-11-06. Repozytorium: `Pawcio99/ETA_FULL_BSD`.
Baza repozytorium: `ec1acabacd9d3bb204bef331004745e0a9f5c234`.
Tryb: SOURCE REVIEW + OFFHOST FUNCTION REPRODUCTION, nie odbiór produktu.

## 1. Pochodzenie i ograniczenia

Odnaleziono prywatne materiały projektu `03_ETA_INSTALLED_SOURCE.txt` oraz `04_ETA_CONTRACT_FACTORY_AND_REVIEW.txt` (transfer R3 z 2026-11-04). Dokumenty zawierają kod i deklarowane piny:

- zainstalowane `agentctl.py`: `9ad0f1c3d47b92118e7cc2da87240b72b05032c7745419dc989394f02cd5d488`;
- `cherub_flow.py`: `95396b35368762fe66e5c5f5feb3b28f9f6507d294218441253c0e5640d6826c`;
- istniejący kandydat `agentctl_factory_fix.py`: `28a75d041bd019e5f110de5cae856400547cc712455ce5f8149c15af8bba2bd1`.

Dwa pierwsze piny zgadzają się z przekazanym przez operatora odczytem W01. Jednak oryginalne pliki z biblioteki nie były dostępne do materializacji bajtowej w tej sesji. Nie przeliczono ponownie hashy pełnych modułów. Wykonano testy ręcznie odtworzonych fragmentów funkcji odczytanych z dokumentów. Hash fragmentu nie jest hashem modułu. Nie publikujemy pełnych prywatnych źródeł, manifestów hosta ani receiptów.

Miejsca w źródłach tekstowych: część 03, linie 449–495 (`dispatch_task`), 600–662 (wejście CLI), 823–1010 (registry i rekordy), 1041–1185 (adapter); część 04, linie 747–796 (wcześniejszy factory-fix). Odwołania dotyczą tekstu transferu, nie numerów linii obecnego checkoutu hosta.

## 2. W02: istniejący łańcuch, bez nowego frameworka

`cmd_task_dispatch` -> `_require_dispatch_context` -> walidacja kontraktu/kontekstu -> `admit_operation` -> istniejący `StateLedger(create=False)` -> `MessageRegistry.deliver` -> `dispatch_task.execute` -> `CodexAdapter.run` -> kolektor/bind/verify.

Adapter sprawdza `authorize(...) is True` przed `start(...)`. Zainstalowana wersja wywołuje jednak `start_factory(...)` jeszcze przed wejściem do adaptera. Odnaleziona wcześniejsza poprawka odracza fabrykę przez `deferred_start`; należy ją wykorzystać, nie opracowywać ponownie.

Registry ma ścieżkę trwałą z istniejącym ledgerem. Nie zastępować jej procesowo-lokalnym słownikiem ani nowym ledgerem. W ścieżce trwałej wyjątek po `ledger.dispatch` zachowuje DISPATCHING i wymaga recovery; proponowana zmiana tego nie modyfikuje.

## 3. Ustalenie W08-COLLECTION-01

Po `adapter.run` obie odczytane wersje przerywają jedynie dla nieznanego exit lub `RECONCILIATION_REQUIRED`. Przy rzeczywistych statusach adaptera `FAILED`, `INCOMPLETE`, `NOT_VERIFIED` i `CANCELLED` nadal wywołują `collect_candidate`, `bind_candidate` i `verify_candidate`.

To wykazana luka w proponowanej granicy przekazywania kandydata, NIE dowód automatycznego odbioru ani obejścia OS admission. Odczytane `record_assessment` ma osobne warunki ACCEPTED. Wariant naprawy wymaga decyzji kontraktowej: kolektor kandydata działa tylko dla czystego COMPLETE; diagnostyka nieudanego runu pozostaje zachowana w rekordzie błędu, nie jest usuwana ani przedstawiana jako odebrany kandydat.

## 4. W04: minimalna delta i wpływ

Zachować istniejący factory-fix. Proponowany plik `patches/w08_complete_collection_PROPOSED.diff` dodaje siedem linii przed bind/collect: pełny rekord, integer exit=0, COMPLETE, brak anulowania i błędu. Odmowa używa istniejącego `UnknownOutcome(record=record)`, zachowując RunRecord i brak automatycznego retry. Nie zmienia funkcji admission, stanów ledgera, polityk ani procesu startu.

Diff jest propozycją względem pełnego kandydata o pinie `28a75d...a2bd1`; nie zastosowano go do pełnego modułu. Nie wolno nakładać go na inne drzewo ani na aktywną instalację. Numery hunka wynikają z odtworzonego miejsca funkcji i wymagają sprawdzenia na rzeczywistych bajtach.

## 5. Faktycznie wykonana walidacja

Linux / Python 3.13.5, jeden proces testowy, funkcje wybrane przez AST. Odtworzono logikę `dispatch_task`, `CodexAdapter.run`, `cancel_owned` i rekordów; registry, kontrakty, filesystem kandydata, gate i child są atrapami. Zero rzeczywistych procesów Codexa, połączeń sieciowych, operacji na hoście FreeBSD i bazach stanu. AST selection nie jest sandboxem dla złośliwego kodu; wejście musi być wcześniej ocenione i przypięte.

| Wariant | Wynik oczekiwanego kontraktu | Exit |
|---|---|---|
| Fragment wersji zainstalowanej | 5/15 PASS, 10 FAIL | 1 |
| Fragment wcześniejszego factory-fix | 8/15 PASS, 7 FAIL | 1 |
| Fragment factory-fix + proponowana delta | 15/15 PASS | 0 |
| Błędny hash wejścia | odmowa przed testami, zgodnie z oczekiwaniem | 20 |

Wyniki są testami funkcji na odtworzonym tekście, nie byte-exact E2E. Test pozytywny starej wersji jest FAIL z powodu kolejności fabryka-przed-gate, mimo zwrócenia COMPLETE. Siedem pozostałych przypadków factory-fix: niepełny strumień, brak finalnego wyniku, exit 13, model_error, brak model_reported, inny model oraz anulowanie. Wait error już zachowuje recovery.

Test `tests/w08_dispatch_regression.py` może w dopuszczonym środowisku przyjąć pełne moduły i ich wymagane SHA-256 (`--input-kind full-module`); nadal bada tylko wybrane funkcje i atrapowe porty. W tej sesji użyto jawnego trybu `excerpt`. Pełny moduł, prawdziwy ledger/registry, kolektor, FreeBSD i niezależne recenzje pozostają NOT TESTED / NOT PERFORMED.

## 6. Jedno zamknięte zlecenie dla istniejącego Conductora

ID: `ETA_G1_W08_COMPLETE_COLLECTION_R1`, status PREPARED_NOT_DISPATCHED.

Explorer/Integrator: odzyskać istniejący pełny factory-fix o podanym pinie i jego zależności, bez powtarzania W01; ustalić rzeczywisty kompletny source snapshot. Nie rekonstruować całości modułu z fragmentów. Builder: tylko w dopuszczonym odizolowanym stagingu potwierdzić semantykę kolektora, zastosować minimalną deltę, zachować logi i statusy nieudanego runu. Validator: wykonać 15 przypadków na pełnych przypiętych wejściach, następnie regresję realnego registry/ledgera bez grantu i bez uruchamiania produktu. Security Reviewer: niezależnie sprawdzić kolejność gate/factory, niezmienność admission, recovery oraz rozdzielenie kandydata i diagnostyki.

Jeden właściciel zapisu, dwa niezależne końcowe przeglądy tej samej zamrożonej rewizji, maksymalnie dwie rundy korekt, łącznie najwyżej trzy aktywne wywołania modelu. Model/effort żądany: historyczny profil Sol/ultra; obserwowane ustawienia wymagają dowodu. Nie uruchomiono tu Conductora ani tych recenzentów.

Nie zmieniać `main`, aktywnej instalacji, hostowych zabezpieczeń ani repozytorium AGENTS/MK1. Brakujące pełne `roots`, manifest i checkpoint G0/R2 pozostają odrębnym wejściem; ten przegląd ich nie zastępuje.

## 7. Status końcowy

W01_SELECTED_FILES: poprzedni PASS zachowany, bez retestu. W01_FULL: BLOCKED. W02: PARTIAL_SOURCE_REVIEW. W03: PROVISIONAL, bez nowych dowodów hostowych. W04: konkretna delta W08 przygotowana, nie odebrana. G0: BLOCKED. G1: NOT ACCEPTED. Natywne wykonanie: NOT TESTED. Admission: NOT GRANTED. Niezależne recenzje: NOT PERFORMED.
