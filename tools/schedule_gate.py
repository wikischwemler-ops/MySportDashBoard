"""Entscheidet, ob der geplante Lauf jetzt stattfinden soll.
GitHub-Zeitpläne laufen in UTC. Der Workflow läuft alle 2 Stunden von 4:07 bis 22:07 UTC
(deutsche Zeit je nach Sommer-/Winterzeit 5:07 bzw. 6:07 bis 23:07 bzw. 0:07 Uhr); diese Läufe finden immer statt.
Für die frühere nächtliche Variante (Cron 22:07/23:07 UTC) wählt das Skript den Lauf, der 0:07 Uhr deutsche Zeit trifft.
Manuell gestartete Läufe und Pushes laufen immer."""
import datetime as dt, os
from zoneinfo import ZoneInfo
ev = os.environ.get("GITHUB_EVENT_NAME", "")
cron = os.environ.get("SCHEDULE", "")
offset_h = int(dt.datetime.now(ZoneInfo("Europe/Berlin")).utcoffset().total_seconds() // 3600)
if ev != "schedule":
    run = True
else:
    nightly = cron.startswith("7 22 ") or cron.startswith("7 23 ")
    run = not nightly or (cron.startswith("7 22") and offset_h == 2) or (cron.startswith("7 23") and offset_h == 1)
print(f"Ereignis={ev} Zeitplan='{cron}' Berlin=UTC+{offset_h} → run={str(run).lower()}")
with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
    f.write(f"run={'true' if run else 'false'}\n")
