# Projekt MySportDashBoard (Garmin-Dashboard)

Sprache: Deutsch. Stand: 25.10.2026.

## Ziel

Dashboard für Garmin-Connect-Daten der letzten 4 Jahre (Laufen, Rad, Schwimmen, Sonstiges, Fitness & Last, Gesundheit, Prognosen, Einzelaktivitäten mit Verläufen). Eine **feste HTML-Hülle** (`index.html`) liest die Daten aus JSON. Bei Updates ändern sich nur die Daten, nicht das HTML.

## Architektur

| Teil | Datei | Aufgabe |
|---|---|---|
| Abruf | `garmin_export.py` | Login über Token-Ordner `.garminconnect`, holt Aktivitäten, Tages-/Wochen-/Bereichswerte mit Cache (`cache/`, nur neue Tage; Tage älter als 3 Tage gelten als abgeschlossen). Schreibt `data.json`/`data.js` und `activities.json`/`activities.js`. `activity_detail()` lädt Verläufe je Aktivität nach `cache/details/`. |
| Lokales Programm | `garmin_dashboard.py` | Webserver `127.0.0.1:8765`, Auto-Update alle `refresh_hours`, API: `/api/status`, `POST /api/update[?full=1]`, `/api/activity/<id>`, `POST /api/shutdown`. Sperrt `cache/`, `.garminconnect/`, `*.py`, `config.json`. |
| Oberfläche | `index.html` | Chart.js 4.4.1 (cdnjs), Reiter je Gruppe, Monatskalender, Detailansicht. Lädt `data.json`/`activities.json` per `fetch`, Fallback `data.js` (Doppelklick ohne Server), auf Pages verschlüsselt über `site.json` + `*.enc`. |
| Pages-Build | `tools/build_pages.py` | Im Workflow: Export, bis zu `MAX_NEW_DETAILS` (250) Detailverläufe pro Lauf (neueste zuerst), AES-256-GCM mit PBKDF2 (250.000 Runden) aus `DASHBOARD_PASSWORD`, schreibt `site/` (`index.html`, `data.enc`, `activities.enc`, `details/*.enc`, `site.json`). Zwischenspeicher `state.enc` über `actions/cache`. |
| Workflow | `.github/workflows/garmin-sync.yml` (Vorlage: `tools/garmin-sync.yml`) | Nachts 0:07 Uhr deutsche Zeit (Cron 22:07 und 23:07 UTC, `tools/schedule_gate.py` wählt je nach Sommer-/Winterzeit), manuell mit `full` und `max_details`. Secrets: `DASHBOARD_PASSWORD` (Pflicht), `GARMIN_TOKENS` (empfohlen, bei 2FA nötig; erzeugen mit `tools/garmin_tokens_fuer_github.bat`; altes und neues Format `garmin_tokens.json`) oder einzeln `GARMIN_DI_TOKEN`, `GARMIN_DI_REFRESH_TOKEN`, `GARMIN_DI_CLIENT_ID`, optional `GARMIN_EMAIL`/`GARMIN_PASSWORD`. |
| Windows-Helfer | `Dashboard_starten.bat`, `Nur_aktualisieren.bat`, `Taeglich_automatisch.bat` (Aufgabe 06:40), `EXE_bauen.bat` (PyInstaller), `_umgebung.bat` (sucht py/python/uv) | |
| Konfiguration | `config.json` | `tokens`, `years`, `refresh_hours`, `port`, `open_browser` |

Aufrufe: `python garmin_export.py [--years 4] [--tokens PFAD] [--full]`, `python garmin_dashboard.py [--update-only [--full]]`. Abhängigkeit: `garminconnect>=0.2.25` (Workflow zusätzlich `cryptography`).

Nie ins Repository (steht in `.gitignore`): `.garminconnect/`, `cache/`, `data.*`, `activities.*`, `work/`, `site/`, `state.enc`.

## Datenformat (`data.json`)

- `meta {source, title, generated, generated_at, from, to, activities}`
- `groups [{id, label, key}]`: `all`, `run`, `bike`, `swim`, `other`, `fit`, `health`, `pred` (nur Gruppen mit Daten).
- `series {"<gruppe>.<name>": {group, label, unit, freq: "month"|"week", fmt: "num"|"pace"|"time"|"status", agg: "sum"|"avg"|"last", better: "up"|"down"|"none", dec, d: [[schlüssel, wert], …]}}`. Neue Kennlinien in `build()` über `add(...)` anlegen.
- `extra {loadfocus, status}`: Wochenwerte für Load-Fokus und Trainingsstatus.
- `activities.json`: `{generated_at, activities: [{id, d, time, sp, t, name, km, dur, elev, hr, maxhr, pwr, cal, te, race}]}`.

Vorhandene Kennlinien in `fit`: VO2max Laufen/Rad, Fitnessalter, Ausdauerwert, Hill Score, ATL, CTL, ACWR, Load-Fokus (3), Trainingsstatus, Intensitätsminuten, Laktatschwelle HF/Pace/Leistung. In `health`: Ruhepuls, HRV, Schlafdauer, Schlafwert, Stress, Body Battery, Atemfrequenz, SpO₂, Schritte, Gewicht, Körperfett, Fettmasse, fettfreie Masse, Skelettmuskelmasse, Knochenmasse, Körperwasser, BMI (Index-Waage, Zusammensetzung erst ab Dez. 2024, Gewicht vorher nur 4 manuelle Einträge 2024). In `pred`: Prognosen 5 km, 10 km, HM, Marathon.

Sportzuordnung über `RUN`, `BIKE`, `SWIM` in `garmin_export.py`, alles andere ist „Sonstige“. Ändert sich der Inhalt der Detailverläufe, `DETAIL_VERSION` erhöhen (alte Cache-Dateien werden dann neu geladen).

## Garmin: Erkenntnisse

- Token-Reihenfolge: `--tokens`, `config.json`, `.garminconnect` neben dem Programm, `%USERPROFILE%\.garminconnect`. Tokens halten etwa ein Jahr.
- Der erste Lauf über 4 Jahre dauert 20 bis 60 Minuten (Gesundheitswerte nur tageweise). `PAUSE = 0.25 s` zwischen Aufrufen schont das Rate-Limit.
- Rad-Duplikate (gleiche Fahrt als „Cycling“ und „Road Cycling“) können die Radkilometer erhöhen.
- Schlafdaten sind lückenhaft, HRV und Ruhepuls daher mit Vorsicht deuten.
- Körperzusammensetzung (`get_body_composition`): `CHANGE_LOG`/`USER_SETTING` sind Profilangaben, keine Wiegungen (z. B. 31,8 oder 38 kg). 17.03. bis 17.06.2025 springen Fett, Muskel und Knochen bei gleichem Gewicht (falsche Waagen-/Profileinstellung, zeitgleich mit dem VO2max-Ausreißer); ausgeschlossen über `config.json` → `bodycomp_exclude`. Einzelne Fehlmessungen (Körperfett > 4 Prozentpunkte vom Fenster-Median) verwirft der Export.
- Garmin-MCP in Claude Code (`mcp__garmin__*`): `get_progress_summary_between_dates` mit `metric: distance` liefert **Zentimeter** (÷ 100000 = km). Bei „Garmin login failed“ neu authentifizieren (`garmin-mcp-auth`) und Server neu starten.
- Garmin blockiert eventuell Anfragen aus GitHub-Rechenzentren; dann scheitert der Workflow beim Login, lokal läuft alles weiter.

## Referenzwerte VO2max (aus früherem Chat)

14.10.2022: 54,1 · 31.12.2022: 53,2 · 31.03.2023: 53,8 · 30.06.2023: 54,5 · 30.09.2023: 55,6 · 31.12.2023: 55,7 · 31.03.2024: 54,8 · 30.06.2024: 57,5 · 30.09.2024: 56,9 · 31.12.2024: 56,8 · 31.03.2025: 67,4 · 30.04.2025: 70,8 · 30.06.2025: 60,1 · 30.09.2025: 58,2 · 31.12.2025: 55,5 · 31.03.2026: 56,4 · 30.06.2026: 55,9 · 14.10.2026: 56,1.
Das Frühjahr 2025 mit 67 bis 71 ist ein Ausreißer (Garmin-Schätzung).

Gesamt seit 14.10.2022 (Stand früherer Chat): ca. 6.700 km Laufen, 7.846 km Rad, 304 km Schwimmen, 265 km Sonstiges, 1.230 Aktivitäten.

## Offene Aufgaben

1. Ersten Export lokal laufen lassen (`Dashboard_starten.bat`), noch gibt es kein `data.json`.
2. GitHub Pages einrichten: Source „GitHub Actions“, Secrets anlegen, Workflow einmal manuell starten (siehe README).
3. VO2max-Ausreißer im Frühjahr 2025 im Dashboard kennzeichnen (braucht eine Layout-Erweiterung, nur auf ausdrücklichen Wunsch).
4. Kennlinien HF gegen Pace/Geschwindigkeit über alle 4 Jahre, Punkte nach Saison gefärbt. Filter: Laufen ab 5 km und unter 15 Hm/km; Rad ab 20 km ohne Gravel/Alpen und ohne Duplikate; Schwimmen nur Bahn ab 1000 m ohne Intervalle (Tempo über Zeit statt HF).
5. Highlights/Rennen hervorheben (`race`-Flag ist vorhanden). Highlights 2026: Innsbruck Alpine Trailmarathon K42 (02.05., 5:46:23), HALB-Traum 60 (16.05., 8:16:25), Lauingen Multisport (07.06., 4:48:18), Allgäu Panorama Ultra 72,7 km/3.200 Hm (09.08., 8:46:00), Einstein Marathon Ulm (27.09., 2:58:43).
6. Analyse „Trainingseffekt“ für den Alb Ultra Trail (24.10.2026): Hat die Vorbereitung gereicht? Vorläufiger Eindruck bis 14.10.: starke Grundlage, Taper unauffällig.

## Feste Nutzerregeln

- Garmin-Workouts: In jedem Schritt und jeder Einheit immer die HF-Zonenangabe mit Zone und bpm angeben, z. B. „Z2 130-148 bpm“. Gilt immer.
- Norwegisches 4x4 (VO2max): Workouts mit Präfix `NTNU_` benennen, Suffix frei wählbar (z. B. `NTNU_4x4`); regelmäßig einplanen.
- `index.html` nur ändern, wenn der Nutzer ausdrücklich eine Layout-Erweiterung verlangt; sonst nur Export/Daten anpassen.
- Persönliche Daten und Tokens nie committen oder unverschlüsselt veröffentlichen.

## Rennkalender und Trainingsziele (Okt 2026 bis Aug 2027)

- Ziel: Ironman Langdistanz 2027; vorher Olympische Distanz am 22.08.2027 und 70.3 Ironman am 29.08.2027.
- Einstein Marathon Ulm 27.09.2026 (Ziel unter 3:00, erreicht in 2:58:43).
- Biberacher Genießerlauf (Halbmarathon) 18.10.2026 als entspannter Spaßlauf, ca. 1:40.
- Alb Ultra Trail 60 km / 1.800 Hm am 24.10.2026.
- Nikolauslauf Tübingen (Halbmarathon) 06.12.2026, Ziel ca. 1:24 (realistisch ca. 4:00 min/km).
- Wochenstruktur: Laufen Di/Do/So, Schwimmen 3x pro Woche mit klarem Fokus. Powermeter fürs Rad wird angeschafft, danach FTP-Test und wattbasiertes Training.
