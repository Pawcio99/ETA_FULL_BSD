# ETA I3 / M2 — deterministyczny input do FreeBSD pkg-create (R1)

Data: 2026-11-06. Tryb: **OFFHOST SOURCE_ONLY, BUILD_INPUT_PREVIEW**. Projekt: ETA_CHERUB FULL / FreeBSD 15.1. Nie jest to pakiet `.pkg`, instalator hostowy, produkt FULL ani zezwolenie na wykonanie `pkg`.

## Powód przyrostu

I3 M0/M1 zakończył działający cykl instalacji i rollbacku w jednorazowym katalogu Linux. Nie zmieniamy tej implementacji i nie przenosimy jej bezpośrednio na FreeBSD (sama odmawia). Ten odrębny przyrost przygotowuje **dane wejściowe** do ewentualnego natywnego `pkg create`, bez aktywnej instalacji, bez użycia root i bez uruchomienia modułów ETA.

Dokumentacja FreeBSD 15.1: `pkg-create(8)` obsługuje `pkg create -n -r <rootdir> -M <manifest> -o <outdir>`. To deklaracja interfejsu, nie wynik natywnego testu. Referencja: https://man.freebsd.org/cgi/man.cgi?query=pkg-create&sektion=8

## Implementacja

- `installer/m2_pkg_preview.py` przyjmuje istniejący prywatny pakiet W09 i weryfikuje go poprzez `eta_i3_package.load_package` oraz przypięte sumy pięciu modułów.
- Tworzy deterministyczny ZIP zawierający `+MANIFEST`, `STAGE_SOURCE_SHA256SUMS`, README oraz pięć bajtowo niezmienionych plików w `stage/usr/local/share/eta-full-bsd-five-module-preview/tools/`.
- Manifest deklaruje `FreeBSD:15:amd64`, ale nazwę wersji `0.0.0_1` i nieprodukcyjnego maintenera `not-for-distribution@example.invalid`. Nie ma żadnych skryptów instalacyjnych, state DB, grantów, usług, rc.d ani aktywnej ścieżki `/usr/local/libexec/eta-cherub-full`.
- Generator celowo odmawia pracy jako root lub na systemie innym niż Linux. Wymaga `python -I -B`; tworzy tylko jawnie wskazany nowy plik ZIP (`O_EXCL`), nigdy nie nadpisuje.
- `installer/test_m2_pkg_preview.py` bada wejście, powtarzalność ZIP, ABI, dokładny inwentarz, tryby, brak skryptów, kolizje ścieżek, błędny hash, zmienione źródło, niezgodny scope, stare schema v1, CLI i odmowę nadpisania.

## Faktyczne testy i provenance

- Środowisko: Linux/Python 3.13.5, UID/GID 65534, proces bez uprawnień root.
- Wykonano: 18 unittest, 18 PASS, 0 FAIL, exit 0.
- Piny generatora / testu SHA-256: `4010b8a8a0acd5d94691cfd4a3ef71b85922b245c8e5c51b65815eae936378d5` / `dcd262b205b35b6e310b9627d8a6ef1c52e43b287b9fa6ce1b37c05ed5338944`.
- Wejściowy ZIP pięciu modułów: `023cfa3776f37d9911a18661ff0d6920e3aa68476467b6a5eaeecb209a532b41`, 113340 B.
- Wynikowy prywatny input M2: `d0a1ebd88c0b1dd13692beefd01a5a074e84d133f7c6fe01bc76c4c77c728d0e`, 113848 B; dziewięć regularnych pozycji, pięć plików źródłowych.
- Prywatny transport: `ETA_I3_M2_PKG_CREATE_INPUT_R1.zip`, SHA-256 `bff45d77db648a553e8d2eb52e595152e43d008a4b276dd47c2ca44e516b99ee`, 7 plików, 6 wierszy manifestu; NIE publikować w repo publicznym.

Zestaw 18 testów oczekuje prywatnego wejścia `installer/ETA_W09_CORE_LAB_R1.zip` obok testu (lokalny fixture, `*.zip` ignorowany w publicznym repo). Wolno je skopiować tylko do oddzielnie dopuszczonego, prywatnego środowiska testowego. Zmienione bajty wejścia lub brak pakietu powodują odmowę przed generowaniem. Test nie wymaga FreeBSD.

## Zakres następnego odbioru

**M2_NATIVE_PKG_CREATE=NOT_TESTED**. Celem przyszłego, *odrębnie zatwierdzonego* przebiegu M2 jest przyjęcie dokładnie tego wejścia w odizolowanym FreeBSD 15.1, niezależna kontrola manifestu i stagingu, zbudowanie `.pkg` bez instalacji, sprawdzenie `pkg info -F` oraz zgodności zawartości. Komenda `pkg create` nie może być wykonywana na aktywnym hoście bez konkretnej zgody i planu skutków. `pkg add`, uruchomienie produktu, tworzenie bazy, jail/ZFS/PF/VPN/DNS lub modyfikowanie aktywnego katalogu pozostają zabronione.

Nie traktować `pkg` ze scope `FIVE_MODULE_LAB_CORE` jako kompletnej dystrybucji ETA. Formalna promocja wymaga pełnego grafu zależności i licencji, faktycznego `maintainer`, profilu Python 3.12, odebranych W09 oraz instalatora, niezależnych końcowych recenzji i bramek MK-2.1. W29 pozostaje opcjonalny tylko na bazowym zatwierdzonym profilu.

Status: `M0/M1=PASS_TECHNICAL_LIMITED`; `M2_INPUT_PREVIEW=PASS_18_OF_18`; `M2_NATIVE_BUILD=NOT_TESTED`; `M3_NATIVE_INSTALL=BLOCKED_NOT_AUTHORIZED`; `INDEPENDENT_REVIEWS=NOT_PERFORMED`; `G0/G1/G2/G7=NOT_ACCEPTED`.
