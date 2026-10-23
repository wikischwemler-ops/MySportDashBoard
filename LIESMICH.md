# Garmin Dashboard – eigenständiges Programm

Zeigt deine Garmin-Connect-Daten der letzten 4 Jahre als Kennlinien: Laufen, Rad, Schwimmen, Sonstige, Fitness & Last, Gesundheit und Prognosen.
Läuft komplett auf deinem Rechner. Angemeldet wird nur über den Token-Ordner `.garminconnect`, ein Passwort wird nie gespeichert.

## Starten

1. Python 3.10 oder neuer installieren (bei python.org „Add to PATH“ anhaken), **oder** einmal `EXE_bauen.bat` ausführen und danach nur noch `GarminDashboard.exe` verwenden.
2. Doppelklick auf **`Dashboard_starten.bat`**.
3. Der Browser öffnet `http://127.0.0.1:8765`. Das Konsolenfenster offen lassen, solange du das Dashboard nutzt.

Beim **ersten Start** werden 4 Jahre geladen. Das dauert etwa 20–40 Minuten, weil Garmin Gesundheitswerte nur tageweise herausgibt.
Danach werden nur noch neue Tage geholt, das dauert Sekunden.

## Anmeldung über `.garminconnect`

Das Programm sucht den Token-Ordner in dieser Reihenfolge:

1. Pfad in `config.json` → `"tokens"` (Standard: `%USERPROFILE%\.garminconnect`, also z. B. `C:\Users\HP840G6\.garminconnect`)
2. Ordner `.garminconnect` **direkt neben dem Programm**
3. `%USERPROFILE%\.garminconnect`

Sind keine gültigen Tokens da, fragt das Konsolenfenster einmalig nach E-Mail, Passwort und ggf. dem Zwei-Faktor-Code. Danach werden nur die Tokens gespeichert.
Die Tokens werden bei jedem Lauf aufgefrischt und bleiben etwa ein Jahr gültig. Danach fragt das Programm einfach erneut.

## Auf einem anderen Computer

1. Den ganzen Ordner kopieren (USB-Stick, Cloud).
2. Deinen Ordner `C:\Users\HP840G6\.garminconnect` **in diesen Ordner** kopieren, sodass `…\Garmin_Dashboard\.garminconnect\` entsteht.
   In `config.json` dann `"tokens": null` setzen oder die Zeile so lassen: Ist der Standardpfad leer, nimmt das Programm automatisch den Ordner daneben.
3. `Dashboard_starten.bat` bzw. `GarminDashboard.exe` starten.

Der Ordner `cache\` kann mitkopiert werden, dann entfällt der lange erste Abruf.
**Achtung:** `.garminconnect` ist dein Zugang zu Garmin Connect. Nicht öffentlich teilen.

## Reiter „Aktivitäten“

Monatskalender mit jeder einzelnen Aktivität und Wochensummen. Ein Klick auf eine Aktivität zeigt alle Verläufe, die Garmin dafür liefert:
Herzfrequenz, Pace bzw. Tempo, Höhe, Leistung, Kadenz, Laufdynamik, Atemfrequenz, Leistungszustand, Stamina, Temperatur und beim Schwimmen Zugfrequenz und SWOLF.
Dazu kommen Zeit in HF-Zonen, Strecke und Runden. Zum Vergrößern im Diagramm ziehen, die x-Achse lässt sich zwischen Zeit und Distanz umschalten.

Die Verläufe holt das Programm beim ersten Anklicken direkt bei Garmin und legt sie in `cache\details\` ab.
Danach erscheinen sie sofort, auch ohne Internet. Das funktioniert nur, wenn das Dashboard über `Dashboard_starten.bat` läuft.

## Automatisch aktualisieren

- Solange das Programm läuft, aktualisiert es sich alle 6 Stunden (`refresh_hours` in `config.json`) und per Knopf **„Jetzt aktualisieren“**.
- `Taeglich_automatisch.bat` legt eine Windows-Aufgabe an, die jeden Morgen um 06:40 aktualisiert, auch wenn das Dashboard nicht offen ist.

## Dateien

| Datei | Zweck |
|---|---|
| `index.html` | Dashboard (bleibt unverändert) |
| `data.json` / `data.js` | Kennlinien (Monats- und Wochenwerte), werden bei jedem Lauf neu geschrieben |
| `activities.json` / `activities.js` | Liste aller Einzelaktivitäten für den Kalender, getrennt von `data.json` |
| `garmin_dashboard.py` | Programm: Server, Browser, Auto-Update |
| `garmin_export.py` | Abruf von Garmin Connect → `data.json` (auch einzeln nutzbar: `python garmin_export.py --help`) |
| `config.json` | Token-Pfad, Zeitraum, Port, Update-Intervall |
| `cache\` | Zwischenspeicher, damit nur neue Tage geladen werden |

`index.html` per Doppelklick geht auch ohne Programm. Dann werden die zuletzt exportierten Daten aus `data.js` gezeigt, nur ohne Aktualisieren-Knopf.
Für Diagramme und Schriften braucht der Browser Internet.
