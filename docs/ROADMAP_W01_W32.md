# ETA_CHERUB FULL — indeks kart W01–W32

Indeks na podstawie planu MK-2.1 i macierzy z 27.10.2026 (identyfikatory źródeł w `PROJECT_BASELINE.md`). Nie jest aktualną tablicą PASS/FAIL. Każda karta powinna zostać związana z konkretnym commitem/kandydatem oraz dowodem wykonania przed odbiorem.

| Bramka | Karty | Rezultat wymagany do odbioru |
|---|---|---|
| G0 / Z0 | W01 Tożsamość źródła; W02 Inwentarz Conductora/Codex; W03 Host i granice zgód; W04 Minimalna mapa zmian | SOURCE_IDENTITY + REUSE_MAP + HOST_READINESS + IMPLEMENTATION_MAP |
| G1 / Z1 | W05 TaskContract/profil; W06 Freeze kandydata; W07 Komunikaty/idempotencja; W08 CLI wynik/exit/STOP | Prawdziwy przepływ od kontraktu po odebrany artefakt; niezależna walidacja dokładnej rewizji |
| G2 / Z2 | W09 Ledger/checkpoint; W10 Budżet/scheduler; W11 Broker policy/grant; W12 Stagnacja/próby | Trwałość, fail-closed, ograniczona liczba prób, spójna autoryzacja |
| G3 / Z3 | W13 Fakty/sprzeczności; W14 ContextPack; W15 ResearchAdapter; W16 Dyrektor shadow | Wersjonowane informacje, izolacja projektów, decyzje bez sprawczych uprawnień |
| G4 / Z4 | W17 Director–Manager; W18 Profile modeli; W19 REWORK; W20 Obieg decyzji | Jeden automatyczny obieg bez ręcznego transferu między agentami |
| G5 / Z5 | W21 P/E/SMT; W22 Obraz/transport; W23 Runner start/exec/stop; W24 Izolacja/limity | Niezależny odbiór infrastruktury, STOP, limity i natywne dowody |
| G6 / Z6 | W25 Kolektor; W26 Przyrost ETA; W27 Recovery; W28 Archiwum/restore | K1 + odporność na awarie + restore poza hostem |
| Opcjonalne | W29 Benchmark modeli | Nie blokuje pierwszego wydania ze stałym profilem Sol/ultra |
| G7 / Z7 | W30 Manifest release; W31 Promocja/rollback; W32 Drugi projekt/runbook | Odtwarzalne wydanie, bezpieczna promocja, K2/K3 |

## Pierwsza iteracja

`W01 → (W02 i W03 niezależnie) → W04 → G0`. W01 jest aktualnie **BLOCKED** do czasu potwierdzenia tożsamości istniejącego produktu i źródeł. Można przygotować dokumenty i narzędzia source-only bez podnoszenia G0 do PASS. Część projektowa kolejnych modułów może być prowadzona równolegle w zatwierdzonym obszarze, ale nie jest to autoryzacja wykonania.

Nie kopiować kodu lub autoryzacji AGENTS/MK1 do ETA_FULL_BSD; każdą współdzieloną zależność dokumentować jawnie wraz z pochodzeniem i konkretną rewizją.
