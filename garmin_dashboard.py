#!/usr/bin/env python3
"""
Garmin Dashboard – eigenständiges Programm
==========================================
Startet einen kleinen Webserver auf diesem Rechner, öffnet das Dashboard im Browser
und aktualisiert die Garmin-Daten automatisch (beim Start, wenn älter als
'refresh_hours', und auf Knopfdruck im Dashboard).

Angemeldet wird ausschließlich über den Token-Ordner .garminconnect:
  1. Pfad aus config.json ("tokens")
  2. .garminconnect neben diesem Programm  (zum Mitnehmen auf andere Rechner)
  3. %USERPROFILE%\\.garminconnect
Gibt es keine gültigen Tokens, fragt das Programm einmalig im Konsolenfenster nach
E-Mail/Passwort und speichert danach nur die Tokens.
"""
from __future__ import annotations
import json, sys, os, threading, time, webbrowser, datetime as dt, io, contextlib, os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import garmin_export as gx
import socket, urllib.request

APP_VERSION = "2026-10-23 Schwimmbahnen"

APP = gx.app_dir()
WEB = Path(getattr(sys, "_MEIPASS", APP))          # index.html (bei .exe eingebettet)
CFG = {"port": 8765, "years": 4, "refresh_hours": 6, "open_browser": True, "tokens": None}
CFG.update(gx.load_config())

STATE = {"running": False, "last": None, "error": None, "log": []}

class LogTee(io.TextIOBase):
    def __init__(self, orig): self.orig = orig
    def write(self, s):
        if self.orig: self.orig.write(s)
        for line in s.splitlines():
            if line.strip():
                STATE["log"].append(line); del STATE["log"][:-200]
        return len(s)
    def flush(self):
        if self.orig: self.orig.flush()

def data_age_hours():
    p = APP / "data.json"
    return (time.time() - p.stat().st_mtime) / 3600 if p.exists() else 1e9

def has_activity_list():
    """Einzelaktivitäten für den Kalender liegen in activities.json (fehlt bei älteren Versionen)."""
    return (APP / "activities.json").exists()

def update(full=False, interactive=False):
    if STATE["running"]: return
    STATE.update(running=True, error=None)
    try:
        with contextlib.redirect_stdout(LogTee(sys.__stdout__)):
            gx.run_export(CFG.get("tokens"), float(CFG.get("years", 4)), APP, full=full, interactive=interactive)
        STATE["last"] = dt.datetime.now().isoformat(timespec="minutes")
    except Exception as e:
        STATE["error"] = str(e); print("FEHLER:", e)
    finally:
        STATE["running"] = False

_client = {"g": None}
_client_lock = threading.Lock()
def client():
    """Eine angemeldete Garmin-Sitzung für Detailabrufe (nur Tokens, keine Rückfrage)."""
    with _client_lock:
        if _client["g"] is None:
            _client["g"] = gx.login(gx.resolve_tokens(CFG.get("tokens")), interactive=False)
        return _client["g"]

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=str(APP), **kw)
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            return self._json({**STATE, "version": APP_VERSION, "log": STATE["log"][-12:], "age_hours": round(data_age_hours(), 2),
                               "tokens": str(gx.resolve_tokens(CFG.get("tokens")))})
        if path in ("/", "/index.html"):
            f = APP / "index.html"                     # Ordner-Version hat Vorrang (Updates ohne neue .exe)
            if not f.exists(): f = WEB / "index.html"  # sonst die in der .exe eingebettete
            b = f.read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); return self.wfile.write(b)
        if path.startswith("/api/activity/"):
            aid = path.rsplit("/", 1)[-1]
            if not aid.isdigit(): return self._json({"error": "Ungültige Aktivitäts-ID"}, 400)
            try:
                return self._json(gx.activity_detail(client(), int(aid), APP / "cache" / "details"))
            except Exception as e:
                return self._json({"error": f"Details konnten nicht geladen werden: {e}"}, 502)
        if path.startswith("/cache") or path.startswith("/.garminconnect") or path.endswith(".py") or path == "/config.json":
            return self.send_error(404)
        return super().do_GET()
    def do_POST(self):
        if self.path.startswith("/api/shutdown"):
            self._json({"stopping": True, "version": APP_VERSION})
            threading.Thread(target=lambda: (time.sleep(.3), os._exit(0)), daemon=True).start()
            return
        if self.path.startswith("/api/update"):
            full = "full=1" in self.path
            threading.Thread(target=update, kwargs={"full": full}, daemon=True).start()
            return self._json({"started": True})
        self.send_error(404)

class Server(ThreadingHTTPServer):
    # Windows erlaubt sonst einem zweiten Programm denselben Port – dann antwortet weiter die alte Instanz.
    allow_reuse_address = os.name != "nt"   # Windows: exklusiv, Linux/macOS: normal
    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def stop_old_instance(port):
    """Läuft schon ein Dashboard auf diesem Port? Neuere Versionen beenden sich auf Anfrage selbst."""
    try:
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", data=b"", method="POST"), timeout=2)
        print("  Ältere laufende Instanz wurde beendet.")
        return True
    except Exception:
        return False

def bind_server(port):
    stopped = stop_old_instance(port)
    for _ in range(20 if stopped else 1):          # nach dem Beenden kurz auf den freien Port warten
        try:
            return Server(("127.0.0.1", port), Handler), port
        except OSError:
            time.sleep(.5)
    for p in range(port, port + 15):
        try:
            return Server(("127.0.0.1", p), Handler), p
        except OSError:
            if p == port:
                print(f"\n  ACHTUNG: Port {port} ist noch von einem älteren Garmin-Dashboard belegt.")
                print("  Dieses alte Programm läuft im Hintergrund weiter und zeigt alten Stand.")
                print("  Beenden: Task-Manager → Details → python.exe / pythonw.exe (Garmin Dashboard) → Task beenden.")
    raise SystemExit("Kein freier Port gefunden.")

def main():
    print("=" * 56); print("  Garmin Dashboard"); print("=" * 56)
    tok = gx.resolve_tokens(CFG.get("tokens"))
    print("  Programmordner:", APP); print("  Token-Ordner:   ", tok)
    # Erstanmeldung / erster Abruf im Vordergrund (damit E-Mail/Passwort eingegeben werden kann)
    if not (APP / "data.json").exists():
        print("\nErster Start: Daten werden vollständig geladen. Das kann 20–40 Minuten dauern.")
        print("Das Dashboard öffnet sich danach automatisch.\n")
        update(interactive=True)
    elif data_age_hours() > float(CFG.get("refresh_hours", 6)) or not has_activity_list():
        # Login einmal prüfen, damit ggf. nach Zugangsdaten gefragt werden kann
        try: gx.login(tok, interactive=True)
        except gx.LoginError as e: print("Hinweis:", e)
        threading.Thread(target=update, daemon=True).start()
    print("  Programmversion:", APP_VERSION)
    srv, port = bind_server(int(CFG.get("port", 8765)))
    url = f"http://127.0.0.1:{port}/"
    print(f"\nDashboard läuft: {url}\nFenster offen lassen. Beenden mit Strg+C.\n")
    if CFG.get("open_browser", True): webbrowser.open(url)
    # Hintergrund: alle refresh_hours neu laden, solange das Programm läuft
    def loop():
        while True:
            time.sleep(600)
            if data_age_hours() > float(CFG.get("refresh_hours", 6)): update()
    threading.Thread(target=loop, daemon=True).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("Beendet.")

if __name__ == "__main__":
    if "--update-only" in sys.argv:
        update(full="--full" in sys.argv, interactive=True); sys.exit(1 if STATE["error"] else 0)
    main()
