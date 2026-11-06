# G0 — W02/W04: wstępna mapa ponownego użycia (SOURCE_ONLY)

Data odniesienia: 2026-11-06. **Status: PROVISIONAL_NOT_ACCEPTED.** Niniejszy dokument nie jest dowodem odbioru aktualnego Conductora ani przyznaniem prawa do uruchomienia produktu.

## Rozdzielenie czterech tożsamości

1. `installed-product` — istniejące moduły instalacji ETA FULL. Operator uruchomił `tools/w01_source_identity.py`, exit 0, cztery pliki `PASS_SELECTED_FILES_ONLY`. Porównanie podanych SHA-256 do historycznej mapy źródeł dało 4/4 MATCH; samo wywołanie miało `expected_hash_count=0`. Git HEAD, manifest, checkpoint, grant i aktualny host nie zostały w tym wywołaniu atestowane.
2. `conductor-reference` — historycznie wskazany istniejący launcher `08_MODEL_PRACY_MK1/RUN.sh`, role i polityki. Nie zakładać, że jest to aktualny kanoniczny checkout produktu ETA, ani uruchamiać go w celu rozpoznania.
3. `z1-candidate` / `staging.2` — historyczne materiały W05–W08; niepromowane. Nie scalać z instalacją i nie przypisywać wcześniejszych wyników R2 do nieznanej rewizji.
4. `ETA_FULL_BSD GitHub` — repozytorium dokumentacji i przyrostów source-only. Publiczny bootstrap `main` nie jest tożsamy z zainstalowanym produktem ani bieżącym checkpointem.

## W02 — mapa wstępna funkcji

| Zakres | Historyczny punkt integracji | Decyzja | Ograniczenie dowodu |
|---|---|---|---|
| Uruchamianie i delegacja | `08_MODEL_PRACY_MK1/RUN.sh` i konfiguracja ról | KEEP/VERIFY | Historyczny pin `e76bec14741e2eebef76234bd3255299ee2927f3b24fa04d0ab75c91c51a65ed`; bieżący plik i aktywny mandat nieodebrane |
| CLI/dispatch | `tools/agentctl.py` | ADAPT | Bajty zainstalowanej wersji potwierdzone, semantyka `task-dispatch` nieatestowana natywnym testem |
| Przepływ zadań | `tools/cherub_flow.py` | ADAPT | HASH MATCH, rzeczywisty transport/idempotencja, STOP i retry wymagają mapy kodu |
| Stan i checkpointy | `tools/cherub_state.py` | KEEP/ADAPT | HASH MATCH, lecz trwały stan/ledger chroniony i niedostępny; nie odczytywać przez EACCES |
| Kontrakt zadania | `tools/cherub_task_contract.py` | ADAPT | HASH MATCH, testy profilu i aktualny format kandydata nieodebrane |
| Mechanizm freeze/recenzji | staging `WARSZTAT-01-Z1`, moduł `cherub_candidate.py` | VERIFY | Nie potwierdzono dokładnej aktualnej rewizji staging.2, manifestu ani związku z historycznym R2 |
| Adapter Codex model/effort | konfiguracja + dotychczasowy launcher | VERIFY | Sol/ultra wymagany w planie; faktycznie zaobserwowany model/effort brak poświadczenia |

## W04 — robocze przypisanie najbliższego przyrostu G1

| Karta | Pierwszy punkt proponowanej zmiany | Najmniejszy test rozstrzygający |
|---|---|---|
| W05 | `cherub_task_contract.py` + dane profili w dopuszczonej kopii kandydata | Niepełny, niezgodny lub nieautoryzowany profil nie przechodzi walidacji; nie przyznaje grantu |
| W06 | istniejąca granica `cherub_candidate.py` + proces zamrożenia | Builder nie może modyfikować dowodów, aktywnej polityki ani frozen candidate; hash mismatch blokuje |
| W07 | `cherub_flow.py`, istniejąca ścieżka stanu | Duplikat message_id, stale plan, obcy projekt i impersonacja roli są odrzucane |
| W08 | `agentctl.py` oraz adapter uruchomienia `RUN.sh` | Exit != 0, niepełna finalizacja i STOP bez ownership nie mogą stać się PASS |

**Nie zaczynać Buildera na niezweryfikowanym stagingu.** W05–W08 wymagają dokładnego source snapshot; przyrosty dokumentacyjne i projektowanie testów mogą postępować równolegle.

## W03 — granica aktualnego hosta

- Historia wskazuje FreeBSD 15.1, ZFS, RACCT/VIMAGE, częściowy odbiór infrastruktury B0 i brak autentycznego admission w innych przebiegach. To nie jest świeża atestacja.
- Nie przenosić zgód B0/A2 na G0/G1; brak odrębnej decyzji oznacza brak uruchomienia produktu, jaili, VM, instalatorów i reguł root.
- Stan PF/VPN/DNS/boot/ZFS pozostaje bez zmian. W03 dokumentacyjny może postępować bez dopuszczenia obciążenia.
- Opublikowany kod GitHub, test source-only i sukces W01 dla wybranych plików nie zastępują `HOST_READINESS`, checkpointu ani aktywnego mandatu.

## Następny dowód w jednym przebiegu

Użyć `tools/g0_ro_inventory.py` z **dokładnym SHA-256 przypiętym do commitu repozytorium**, wyłącznie na wcześniej wskazanych katalogach: zainstalowany produkt, Conductor, kandydat Z1 i zamrożona rewizja (jeśli istnieje). Narzędzie odczytuje metadane i wybrane niesekretne hashe, nie odczytuje zawartości sekretów ani stanu; 15 testów offhost na syntetycznych danych przeszło, ale nie ma natywnego testu FreeBSD. Nie duplikować już zaliczonego porównania czterech modułów.

**Status końcowy:** `W01_SELECTED_FILES=PASS_4_OF_4`; `W01_FULL_SOURCE_IDENTITY=BLOCKED`; `W02=PROVISIONAL`; `W03=PROVISIONAL`; `W04=PROVISIONAL`; `G0=BLOCKED`.
