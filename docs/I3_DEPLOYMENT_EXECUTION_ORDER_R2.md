# ETA_CHERUB FULL / FreeBSD 15.1 — ścieżka do pierwszej instalacji laboratoryjnej (I3 R2)

Data: 2026-11-06. Status: `IMPLEMENTATION_ORDER_PREPARED`, nie grant wykonania ani odbiór. Właściwe repo: `Pawcio99/ETA_FULL_BSD`, publiczne. Nie przenosić prywatnych źródeł, receiptów, bazy ani danych z AGENTS/MK1.

## Zdefiniowane cele

- **M0: SOURCE_ONLY_INSTALLER_CANDIDATE** — w pełni odtwarzalny pakiet i manifest, kontrola wejścia, generowanie planu zmian, walidacja uprawnień i wersji, odmowy dla błędnych danych. Bez kontaktu z aktywną instalacją.
- **M1: DISPOSABLE_ROOT_INSTALLATION** — testowane apply/status/verify/rollback w nowym jednorazowym katalogu/obrazie, bez uprawnień root, bez uruchomienia produktu i poza rzeczywistym hostem FreeBSD.
- **M2: FREEBSD_NATIVE_BUILD_ONLY** — zbudowanie i weryfikacja zgodności pakietu w oddzielnie dopuszczonym FreeBSD 15.1, bez jego instalowania i bez skryptów startowych. Potwierdzić aktualne możliwości `pkg create -r <staging-root> -M <manifest>` z `pkg-create(8)`; ostateczny format po mapie istniejącego instalatora.
- **M3: APPROVED_LAB_INSTALL** — oddzielna zgoda na konkretny cel i plan skutków, jedna wersja, niezależny readback, negatywne próby, przerwanie i kontrolowany rollback. Dopiero po odbiorze granic danego celu, a jeśli rzeczywiście wykonujemy produkt: właściwe admission/G5 i zależne bramki.
- **M4: FULL_MK2.1_RELEASE** — G0–G7, K1–K3, osobne promotowanie, W25→W27A→W26→W27B/W28→G6→W30–W32; nie mylić M3 z pełnym wydaniem.

Wariant pierwszy: **FRESH_INSTALL / NEW_STATELEDGER_V2** w nowym izolowanym celu, bez migracji i bez podmieniania działającej bazy v1. Wariant `UPGRADE_V1_TO_V2` wymaga własnego odbioru, zabezpieczonego backupu SQLite, weryfikacji stanu/lease i oddzielnej zgody operatora. Stara wersja v1 ma pozostać nienaruszona; v2 odmawia jej bez migracji.

## Kontrakty niezmienne

`source_digest`, `package_digest`, `manifest_digest`, `policy_digest`, `target_identity`, `state_schema_version`, `rollback_identity`, `test_digest`, `environment_digest`.

Dozwolony cel jest wyłącznie jawnie enumerowany — bez zgadywania ścieżek użytkownika, rekursywnych zapisów poza zakresem, symlink-follow, TOCTOU bez kontroli, usuwania istniejącego stanu, przekierowań na aktywny produkt i startu usług przy samym rozpakowaniu. PLAN nie tworzy katalogów, blokad ani plików. STAGE jest osobno dopuszczoną operacją w izolowanym workspace. APPLY i uruchomienie produktu wymagają kolejnych odrębnych zgód; nie istnieje niejawne dziedziczenie uprawnień z GitHub PR, Codexa lub instalatora.

Stany logiczne: `PLANNED`, `STAGED`, `APPLYING`, `INSTALLED_UNVERIFIED`, `VERIFIED`, `RECOVERY_REQUIRED`, `ROLLED_BACK`. Nie traktować `INSTALLED_UNVERIFIED` jako PASS. Jeśli rollback jest niebezpieczny wskutek niezgodnej bazy lub nieznanego skutku, pozostawić `RECOVERY_REQUIRED`.

## Pakiet wykonawczy dla istniejącego Conductora: ETA_I3_INSTALLER_VERTICAL_R1

1. **Explorer / integration:** zidentyfikować aktualny, naprawdę istniejący mechanizm instalacji i aktywny layout ETA; opisać `KEEP/ADAPT/ADD`, zależności Pythona i FreeBSD, sposób pakowania oraz różnice do W09 v2. Nie zakładać z góry `pkg` ani nowego installera. Rozstrzygnąć rzeczywiste ścieżki i zakresy, ale nie publikować sekretów lub nazw baz aktywnego hosta.
2. **Builder / jedyny piszący:** w dopuszczonym offhost workspace wykonać `M0` i `M1`: manifesty i kompletne źródła, plan read-only, prywatny staging, instalacja w jednorazowym katalogu/obrazie, verify/status, kontrolowane wycofanie. Instalator nie jest brokerem i nie przyznaje grantu. Wersja produktu nie musi wchodzić w działające usługi w tym kroku.
3. **Validator:** testy deterministycznego pakietu i fałszywego sha, traversal/symlinks, konfliktu wersji/owner, idempotentnego ponowienia, przerwanej operacji, braku śladów poza root testowym, rozdzielenia pakietu od stanu v2, zgodności v1/v2 (odmowa automigracji), readback i rollbacku. Przypiąć surowe logi i exit do frozen commit.
4. **Security Reviewer:** niezależnie potwierdzić least-privilege, brak ukrytych root/service/jail/ZFS/PF/VPN/DNS skutków, kontrolę ownership/symlink/TOCTOU, rozdział źródeł, tajemnic, logów i stanu, jednego właściciela, brak automatycznej promocji i możliwość awaryjnego STOP.
5. **Manager / Conductor:** maksimum trzy równoczesne wywołania łącznie, jeden właściciel zapisu, dwie rundy poprawek, dwa odrębne przeglądy jednej rewizji, ≥20% rezerwy. Po M1 przygotować odrębny, konkretny wniosek o dopuszczenie M2, a później M3. Bez wykonywania native apply w ramach tego dokumentu.

## Kryteria odbioru i dowody

`M0`: manifest byte-exact, lista efektów i skutków w `plan`, odmowy dla niedozwolonych wejść, reproducible build w zatwierdzonym zakresie.
`M1`: test faktycznego staging/apply/readback/rollback wyłącznie na disposable root oraz brak zmian poza nim, kontrola stanu po crash; niezależna walidacja.
`M2`: rzeczywiste FreeBSD 15.1 toolchain/ABI/package identity, wynik build-only i kontrola zawartości, bez instalacji i autostartu.
`M3`: operator przyjmuje konkretny zakres, a zewnętrzny validator potwierdza stan po instalacji i po rollbacku; istniejący, nieruszony aktywny system.
`M4`: pełne G0–G7/K1–K3 i zaakceptowane wydanie.

Minimalne artefakty: `SOURCE_BINDING.json`, `PACKAGE_MANIFEST`, `INSTALLATION_PLAN`, `INTEGRATION_MAP`, `TEST_RESULTS`, `VALIDATOR_REPORT`, `SECURITY_REVIEW_REPORT`, `ROLLBACK_PLAN`, `FINAL_REPORT`; każdy wynik z hashami dokładnego kandydata. Nie wymyślać nazw istniejącego CLI.

## Wąskie blokady rzeczywiste

- W09: własny candidate ma `source/cherub_state.py` v2 i `source/cherub_flow.py`; zewnętrzny pakiet `ETA_W09_FAILED_RUN_EVIDENCE_R1.zip` ma zgłoszony SHA-256 `66b5f9834706762325d977d39aac70c99c6f350d5fd54cadc5ac3f8a676e17bb`; 47+13 testów offhost PASS; dwie niezależne recenzje nadal NOT PERFORMED. Formalny G1/G2 nieprzyjęty.
- Kanoniczne drzewo całego produktu: `NOT_ATTESTED` (wybrany snapshot pięciu modułów ≠ kompletna dystrybucja).
- Autentyczne admission, HOST_READY, runner i G5: niezakończone; nie hamują źródłowych M0/M1, lecz blokują natywne execution i późniejsze M3 dla produktu.
- Pełne K1–K3: nadal nieudowodnione. W29 benchmark modelu nie jest warunkiem pierwszego wydania w ustalonym profilu.

## Wymagana decyzja operatora przed mutacją

Po M0/M1: oddzielnie zatwierdzić jedynie **native build-only** na wskazanym izolowanym celu, z dokładnym manifestem komend/skutków. Następnie osobno autoryzować konkretną instalację M3; migracja bazy produkcyjnej v1→v2 wymaga jeszcze innej zgody. Bieżące zlecenie nie zmienia active FreeBSD, repo publicznego `main`, brokera, Conductora ani chronionych polityk.
