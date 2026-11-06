# G0 / W01–W04 — zlecenie wejściowe ETA_FULL_BSD

Tryb: SOURCE-ONLY / HOST-READ-ONLY (gdy operator uruchomi konkretną diagnostykę). Właściciel decyzji: operator istniejącego ETA Conductor. Status G0: **BLOCKED**.

| ID | Produkt | Stan bieżący | Warunek rozstrzygający |
|---|---|---|---|
| W01 | SOURCE_IDENTITY i manifest wejściowy | BLOCKED — GitHub bootstrap ≠ kanoniczny produkt | Dokładny source_root, rewizja/HEAD lub równoważny pin, manifest, checkpoint, katalog wykluczeń i mapa kandydat/aktywny runtime |
| W02 | REUSE_MAP | NOT TESTED dla aktualnej rewizji | Identyfikacja faktycznych punktów dispatch/exit/STOP/receipt, konfiguracji ról, wersji klienta i model/effort z dowodami |
| W03 | HOST_READINESS | BLOCKED dla nowych skutków | Aktualna identyfikacja hosta, ograniczenia i wstrzymania; brak domniemanego zwolnienia po incydencie, brak rozszerzenia historycznych grantów |
| W04 | IMPLEMENTATION_MAP | NOT TESTED | W05–W32 związane z konkretnymi modułami i właścicielami plików, mapa KEEP/ADAPT/ADD, minimalny diff oraz zależności |

## Dostarczony przyrost W01

`tools/w01_source_identity.py` jest narzędziem odczytowym. Nie skanuje dowolnych katalogów ani nie zgaduje `source_root`; hashuje wyłącznie jawnie wybrane pliki zwykłe. Odrzuca symlinki, traversal, niekanoniczne nazwy i zmiany tożsamości pliku w trakcie odczytu; limit 64 plików, 32 MiB na plik. Przyjmuje opcjonalny checkpoint/manifest do **haszowania**, ale nie interpretuje ich jako potwierdzenia autentyczności. Nie uruchamia Git, Conductora, produktu, jaili, VM ani żadnego z pobranych źródeł. Exit 0 oznacza tylko PASS_SELECTED_FILES_ONLY; 20 = MISMATCH; 21 = BLOCKED. Nie wolno z tego wyniku wyprowadzić G0=PASS.

Przykład użycia w już zweryfikowanym, zwykłym kontekście użytkownika FreeBSD, **po potwierdzeniu rzeczywistego źródła**, bez `sudo`:

```sh
# Poniższa ścieżka jest przykładem historycznie raportowanej instalacji,
# NIE zaświadczeniem aktualnej tożsamości ani zamiennikiem repozytorium:
SOURCE_ROOT="/usr/local/libexec/eta-cherub-full/product"
python3.12 -B tools/w01_source_identity.py \
  --source-root "$SOURCE_ROOT" \
  --file tools/agentctl.py \
  --file tools/cherub_flow.py \
  --file tools/cherub_state.py \
  --file tools/cherub_task_contract.py
```

Przed użyciem porównać pochodzenie skryptu z oczekiwanym commitem, nie uruchamiać go z przypadkowego archiwum. Alternatywny source_root z katalogu projektu, zamrożone stagingi i instalacja produktu są różnymi tożsamościami; ich wyników nie scalać.

## Niedopuszczone działania

Żadnych zmian PF/VPN/DNS/boot/sysctl/ZFS, restartów, tworzenia/uruchamiania jaili, hostowego product execution, automatycznego wydania grantów, podmieniania aktywnego Conductora i promocji na `main`. Materiały AGENTS/MK1 są innym projektem.

## Odbiór G0

1. W01: identyfikacja kanonicznego kandydata, HEAD lub pin zawartości, checkpoint, manifest i ewentualne pominięcia; brak nieznanych zmian użytkownika.
2. W02: kompletna mapa KEEP/ADAPT/ADD/UNVERIFIED względem tego samego materiału i rzeczywistego adaptera modelu.
3. W03: stan hosta i aktywne blokady przypisane do konkretnych przyszłych skutków; HOST_READY do obciążeń osobno.
4. W04: konkretna mapa punktów zmian W05–W32, bez tworzenia alternatywnego frameworka.
5. Dwa przeglądy przyrostu źródłowego, wyniki powiązane z jednym zamrożonym commitem. G0 może być rozstrzygnięte dokumentacyjnie bez admission runtime.

**Aktualny wynik**: dostarczono skrypt i testy syntetyczne. W01 źródła FreeBSD, W02–W04, natywne wykonanie i G0 pozostają **NOT ATTESTED / BLOCKED**.
