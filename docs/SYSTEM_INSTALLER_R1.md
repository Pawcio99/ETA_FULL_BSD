# ETA — pierwszy instalator systemowy FreeBSD R1

STATUS: IMPLEMENTED_SOURCE_CANDIDATE / NATIVE_NOT_TESTED. Projekt ETA_CHERUB FULL / FreeBSD 15.1, nie AGENTS/MK1 ani instalator systemu operacyjnego.

## Wykonywalna implementacja

`INSTALL_FREEBSD.sh` uruchamia samodzielny `installer/eta_system_install.py` przez `/usr/local/bin/python3.12 -I -B`. Komendy: inspect, plan, install, verify, status, rollback-plan, rollback, recovery-plan, recover. Brak domyślnej mutacji.

Natywna ścieżka wymaga FreeBSD 15.1-RELEASE/amd64 (także -pN), zgodnego kernela i userlandu, Python 3.12 oraz dostępnych API descriptor-relative. `plan` odczytuje wersję, hostuuid, boot, flagę jail i tożsamość wąskiego zestawu ścieżek. Mutacje wymagają UID/EUID 0, `--allow-system-write` oraz `--confirm-plan` z dokładnym SHA-256 osobno przejrzanego planu. Nie wyliczać zgody automatycznie w poleceniu instalacji. Hash/flag nie są issuerem grantu.

Kod instalatora, interpreter i payload uruchamiane jako root muszą mieć bezpiecznych root-owned rodziców bez group/other-write i symlinków. Nietrywialne/dziedziczone ACL są odrzucane; istniejące ACL/uprawnienia nie są zmieniane. Nie uruchamiać root skryptu z katalogu użytkownika; operator musi niezależnie sprawdzić bajty przed uruchomieniem uprzywilejowanego interpretera. Polecenia przyszłej instalacji znajdują się w prywatnej instrukcji operatora i wymagają oddzielnego dopuszczenia.

## Zakres pierwszej wersji

Instalowane jest pięć niezmienionych przypiętych modułów W08/W09, nie kompletna dystrybucja FULL. Release ID `w09-v2-023cfa3776f37d99`.

Kod: `/usr/local/libexec/eta-cherub-full/releases/w09-v2-023cfa3776f37d99/product/tools/`.
Nowy stan i dziennik: `/var/db/eta-cherub-full-installer/w09-v2-023cfa3776f37d99/`.
Nowe pliki kodu i manifest: 0444, katalogi kodu: 0755, prywatny stan/dziennik: 0700, SQLite: 0600. Root-quarantined state nie jest przekazaniem własności do etactrl ani istniejącego Conductora.

Instalator zapisuje świeżą PUSTĄ bazę v2 na podstawie schematu wyjętego przez AST/literal_eval z przypiętego źródła. Nie importuje/wykonuje modułów produktu jako root. Rzeczywisty StateLedger(create=False) otworzył tak utworzoną bazę w teście offhost. Nie powstaje projekt, budżet, grant, domyślne przydziały ani proces.

Aktywne `.../eta-cherub-full/product/` i `/var/db/eta-cherub-full/state/` pozostają nietknięte. Dodanie nowego podkatalogu zmienia metadane jego rodzica. Nie ma instalacji zależności, rejestracji w pkg, pobierania sieciowego, migracji v1, aktywacji kodu, usług/rc.conf, kont, PF/VPN/DNS, jaili/ZFS ani bootloadera.

## Transakcja i wycofanie

plan -> potwierdzony plan -> STAGING -> STAGED -> STATE_READY -> PUBLISHED -> VERIFIED_INACTIVE. Plan jest bez jawnych zapisów aplikacji; odczyty mogą aktualizować systemowe atime.

Osobny readback sprawdza rzeczywiste pliki, SHA-256, tryby, schemat SQLite, integrity_check, foreign_key_check i brak wierszy, zamiast ufać samemu receiptowi. To nie niezależna recenzja drugiego agenta.

Rollback wymaga własnego planu i zgody. Przenosi kod do `.withdrawn-<release>`, nie usuwa danych ani nie cofa starej bazy. Odmawia przy aktywnym writerze lub niepustym stanie. Recovery ma jawne decyzje complete/abort/complete-withdrawal; nie odtwarza automatycznie bazy i nie ponawia pracy produktu. Niekompletny/uszkodzony dziennik wymaga ręcznego uzgodnienia, bez --force i bez resetowania liczników.

## Faktycznie wykonane testy

69/69 metod PASS, exit 0. Silnik działał na rzeczywistych plikach i SQLite w jednorazowym obrazie katalogów. Siedem scenariuszy przerwania to faktyczne zakończenie procesu os._exit, nie utrata zasilania. Potwierdzono plan bez zapisów, idempotencję, ochronę aktywnych sentinelów, starej bazy, kontrolę hashy, błędnych ścieżek/mode/symlink/hardlink, schema v1, WAL, budżetu instalacyjnego zapisu, konkurencyjnych writerów i rollback zachowujący DB. W tym zestawie nie wykonywano zadań modelu ani testów całej autonomii.

Demo rzeczywiście wykonało install -> verify -> idempotent install -> withdraw -> status na obrazie offhost; final WITHDRAWN_DATA_RETAINED, stare pliki niezmienione, hash nowej bazy przed/po wycofaniu identyczny.

Linux/Python 3.13.5/SQLite 3.46.1, UID/GID 65534, puste supplementary groups, CapEff=0, NoNewPrivs=1, seccomp2, osobny chroot i ograniczenia zasobów. Rzeczywiste próby socket/root-write/chroot odmówione. Sprawdzono składnię Python 3.12, NIE runtime 3.12. Native preflight i libc ACL na FreeBSD są testowane tylko kontraktowo z atrapami, nie na FreeBSD. Kod natywny CLI rzeczywiście odmówił mutacji na Linux.

Threat model: administrator root jest zaufany; flock i własność katalogów nie dają izolacji przed wrogim root. SHA-256 dziennika nie jest niezależnym podpisem. Brak dowodu power-loss/storage durability.

## Integralność i reprodukcja

Skrypt SHA-256 `289f14864668fcba6a118a353338588b2557e547c920c77f6a8c577a0f347e62`.
Test SHA-256 `e52bcf427dbae6c8f738c930d23563af6270d302f203035274d3fda9ff05fd89`.
Payload SHA-256 `023cfa3776f37d9911a18661ff0d6920e3aa68476467b6a5eaeecb209a532b41` (113340 B).

Publiczny checkout celowo nie zawiera prywatnego payloadu. Pełny prywatny pakiet operatora zawiera go wraz ze źródłem instalatora, testami, harness Linux, surowymi logami, manifestem oraz dokładną instrukcją operatora. Do odtworzenia testów potrzebny jest payload w `packages/ETA_W09_CORE_LAB_R1.zip`, odrębny dopuszczony workspace i nieuprzywilejowany Python -I -B. Linux harness NIE jest poleceniem dla stacji FreeBSD.

## Odbiór

OFFHOST_ENGINE=PASS_69_OF_69. NATIVE_FREEBSD=NOT_TESTED. NATIVE_ACL=NOT_TESTED. PYTHON_3_12_RUNTIME=NOT_TESTED. INDEPENDENT_REVIEWS=NOT_PERFORMED. ACTIVE_INSTALLATION=NOT_PERFORMED. ACTIVATION=NOT_IMPLEMENTED. G0/G1/G2/G7 pozostają nieprzyjęte.

Następny krok: tylko inspect i native read-only plan, przegląd dokładnych bajtów i planu; potem odrębna zgoda na konkretny install w odebranym celu. Wnioskowanie z offhost PASS o gotowości produkcyjnej jest zabronione. Nie jest to pełne wydanie ETA.
