# ETA_FULL_BSD — zatwierdzona baza projektowa (dokument referencyjny)

Projekt: **ETA_CHERUB FULL / FreeBSD 15.1**. Nie jest repozytorium AGENTS/MK1, Ubuntu FULL ani CHERUB_VM01.

## Dokumenty nadrzędne — poza repozytorium publicznym

- `ETA_CHERUB_FULL_PLAN_WDROZENIA_WARSZTATU_MK-2.1.txt` (26.10.2026), SHA-256 `a800b93bf407293b92c55854e3cdcdc57c204a2bf4b36fad9f71b11fb03c5ccb`.
- `ETA_CHERUB_FREEBSD_FULL_MATRIX_v0.1_2026-10-27.md`, SHA-256 `4196030cfffa93d680bc4e5086426601795870849b2865936adcd45350c9e6cc`.

Te skróty identyfikują historyczne *dokumenty*. **Nie** poświadczają aktualnego drzewa produktu, instalacji ani wykonania testów. Pełne dokumenty i prywatne dowody pozostają w zatwierdzonym magazynie projektu; do repozytorium publicznego trafiają tylko niesekretne streszczenia i kod narzędziowy.

## Kontrakt wykonania

- Rozwijamy istniejący Conductor ETA. Nie tworzymy drugiego managera stanu, brokera, grantu ani launchera.
- Model żądany przez historyczny plan: `gpt-6.1-sol` / `model_reasoning_effort="ultra"`. Faktyczny model i effort wymagają dowodu z wykonania; brak potwierdzenia oznacza NOT_ATTESTED.
- Maksymalnie trzy aktywne wywołania modelu w systemie, jeden właściciel zapisu na obszar, maksymalnie dwie rundy poprawek, niezależne recenzje tej samej zamrożonej rewizji.
- Stary PASS nie przechodzi na nowy commit, inne środowisko ani osobny projekt.
- Kod, dokumentacja i GitHub CI nie przyznają admission, praw root, zezwoleń jail/ZFS ani prawa do uruchomienia produktu.
- Planowana infrastruktura pilota: jedna VM, 4 vCPU, 4 GiB RAM — parametry projektowe, nie wykonana konfiguracja.
- Zachowujemy rozróżnienie PASS / FAIL / BLOCKED / NOT TESTED. Bramka G0 poprzedza odbiór G1 i kolejne etapy.
- W publicznym repozytorium nie umieszczać tokenów, kluczy, prywatnych profili VPN, danych użytkownika, prywatnych receiptów, aktywnego stanu, konfiguracji uwierzytelnienia ani kopii rootfs.

## Kolejność

`Z0: W01–W04 / G0` → `Z1: W05–W08 / G1` → `Z2: W09–W12 / G2` → `Z3: W13–W16 / G3` → `Z4: W17–W20 / G4`. Równolegle przygotowywane `Z5: W21–W24 / G5` wymagają odrębnych bramek infrastrukturalnych. Dalej `Z6: W25–W28 / G6` → `Z7: W30–W32 / G7`. `W29` jest opcjonalnym benchmarkiem, nie bramką pierwszego wydania.

Status: **BASELINE_DOCUMENTED_ONLY**; rzeczywista tożsamość `source_root`, HEAD/manifest/checkpoint, host readiness i pierwotny punkt integracji wymagają W01–W04.
