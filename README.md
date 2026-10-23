# MySportDashBoard
Garmin DashBoard

Dashboard für Garmin-Connect-Daten der letzten 4 Jahre: Laufen, Rad, Schwimmen, alle Aktivitäten, Fitness & Last (Load-Fokus, Trainingsstatus, Laktatschwelle), Gesundheit, Prognosen und jede einzelne Aktivität mit allen Verläufen.

Es läuft auf zwei Arten:

| | Wo | Daten |
|---|---|---|
| **Zuhause** | `Dashboard_starten.bat` → `http://127.0.0.1:8765` | direkt von Garmin, lokal im Ordner |
| **Unterwegs** | GitHub Pages, z. B. `https://<dein-github-name>.github.io/MySportDashBoard/` | jede Nacht um 0 Uhr vom Workflow geholt, **mit deinem Passwort verschlüsselt** |

---

## Unterwegs: GitHub Pages einrichten (einmalig)

### 1. Repository-Sichtbarkeit
GitHub Pages ist **immer öffentlich erreichbar**, auch bei einem privaten Repository. Deshalb verschlüsselt der Workflow alle Daten mit AES-256. Ohne Passwort sieht man nur die Anmeldeseite.

- Mit **GitHub Free** funktioniert Pages nur bei einem **öffentlichen** Repository. Das ist hier unbedenklich: Im Repository liegt nur Programmcode, deine Daten und Tokens nie (siehe `.gitignore`).
- Mit **GitHub Pro** kannst du das Repository privat lassen.

### 2. Pages aktivieren
Repository → **Settings → Pages → Build and deployment → Source: GitHub Actions**

### 3. Secrets anlegen
Repository → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Inhalt | Pflicht |
|---|---|---|
| `DASHBOARD_PASSWORD` | Dein Passwort für die Seite, mindestens 8 Zeichen | **ja** |
| `GARMIN_TOKENS` | Deine Garmin-Tokens: `tools\garmin_tokens_fuer_github.bat` doppelklicken, dann Strg+V | empfohlen |
| `GARMIN_EMAIL` | Deine Garmin-Connect-E-Mail | optional |
| `GARMIN_PASSWORD` | Dein Garmin-Connect-Passwort | optional |

**Welche Garmin-Anmeldung?**
- Nutzt dein Garmin-Konto die **Zwei-Faktor-Anmeldung**, brauchst du `GARMIN_TOKENS`, denn im Workflow kann niemand den Code eingeben.
- Ohne Zwei-Faktor reichen `GARMIN_EMAIL` und `GARMIN_PASSWORD`.
- Hast du beides angelegt, nimmt der Workflow zuerst die Tokens und meldet sich nur bei Bedarf mit E-Mail und Passwort neu an.
- Die Tokens werden bei jedem Lauf aufgefrischt und verschlüsselt im Zwischenspeicher behalten. Sie halten etwa ein Jahr, danach das Secret einfach neu erzeugen.

### 4. Erster Lauf
Repository → **Actions → Garmin Sync → Run workflow**.

- Der erste Lauf lädt 4 Jahre und dauert etwa 30–60 Minuten.
- Danach werden nur noch neue Tage geholt.
- Die Detailverläufe der Aktivitäten (Herzfrequenz, Pace, Höhe, Schwimmbahnen …) lädt der Workflow schrittweise nach, **bis zu 250 pro Lauf, neueste zuerst**. Nach ein paar Nächten sind alle da. Beim manuellen Start kannst du die Zahl erhöhen.

### 5. Seite öffnen
Die Adresse steht nach dem Lauf unter **Settings → Pages**. Passwort eingeben, fertig. Mit „Auf diesem Gerät merken“ musst du es auf dem Handy nur einmal eingeben, mit „Sperren“ oben rechts löschst du es wieder.

## Wann wird synchronisiert?
- **Jede Nacht um 0:00 Uhr** deutscher Zeit, Sommer- wie Winterzeit. GitHub startet geplante Läufe manchmal einige Minuten später.
- **Sofort:** Actions → Garmin Sync → Run workflow. Mit „Alles neu laden“ wird der Zwischenspeicher ignoriert.

## Sicherheit
- Daten auf Pages: AES-256-GCM, Schlüssel aus deinem Passwort per PBKDF2 (250.000 Runden). Entschlüsselt wird nur in deinem Browser.
- Zwischenspeicher im Workflow (`state.enc`) mit deinen Rohdaten und Tokens: ebenfalls mit deinem Passwort verschlüsselt.
- Ändern von `DASHBOARD_PASSWORD`: Der nächste Lauf baut den Zwischenspeicher neu auf und lädt alles noch einmal.
- Nie ins Repository: `.garminconnect\`, `cache\`, `data.json`, `activities.json` (steht in `.gitignore`).

## Dateien
| Datei | Zweck |
|---|---|
| `index.html` | Dashboard (lokal und auf Pages identisch) |
| `garmin_export.py` | Garmin-Abruf und Berechnung der Kennlinien |
| `garmin_dashboard.py` | Lokales Programm: Server, Browser, Auto-Update |
| `tools/build_pages.py` | Baut im Workflow die verschlüsselte Pages-Seite |
| `tools/schedule_gate.py` | Sorgt für 0 Uhr deutsche Zeit trotz UTC-Zeitplan |
| `tools/garmin_tokens_fuer_github.bat` | Legt deine Tokens als Secret-Text in die Zwischenablage |
| `.github/workflows/garmin-sync.yml` | Der nächtliche Workflow |
| `LIESMICH.md` | Anleitung für die lokale Nutzung |

Hinweis: Garmin bietet keine offizielle Schnittstelle für Privatnutzer. Falls Garmin Anfragen aus GitHub-Rechenzentren blockiert, schlägt der Workflow mit einem Anmeldefehler fehl. Zuhause funktioniert das Dashboard davon unabhängig weiter.
