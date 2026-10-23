#!/usr/bin/env python3
"""
Baut das Dashboard für GitHub Pages (läuft im GitHub-Workflow).

  1. stellt den verschlüsselten Zwischenspeicher (state.enc) wieder her
  2. meldet sich bei Garmin an (gespeicherte Tokens → Secret GARMIN_TOKENS → GARMIN_EMAIL/GARMIN_PASSWORD)
  3. holt neue Daten (inkrementell) und lädt Detailverläufe von Aktivitäten nach
  4. verschlüsselt alle Daten mit DASHBOARD_PASSWORD (AES-256-GCM, Schlüssel per PBKDF2)
  5. schreibt die fertige Seite nach ./site und den Zwischenspeicher wieder verschlüsselt nach state.enc

Ohne DASHBOARD_PASSWORD wird nichts veröffentlicht – GitHub Pages ist öffentlich erreichbar.
"""
from __future__ import annotations
import base64, gzip, io, json, os, shutil, sys, tarfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import garmin_export as gx                      # noqa: E402

from cryptography.hazmat.primitives import hashes                      # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM         # noqa: E402
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC       # noqa: E402

ITER = 250_000
WORK = ROOT / "work"                 # Arbeitsordner im Runner (nicht im Repo)
STATE = ROOT / "state.enc"           # verschlüsselter Zwischenspeicher (über actions/cache)
SITE = ROOT / "site"
MAX_NEW_DETAILS = int(os.environ.get("MAX_NEW_DETAILS", "250"))   # neue Detailabrufe pro Lauf
YEARS = float(os.environ.get("YEARS", "4"))

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)

def derive(pw: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode("utf-8"))

def enc(key: bytes, raw: bytes, compress=True) -> bytes:
    iv = os.urandom(12)
    return iv + AESGCM(key).encrypt(iv, gzip.compress(raw, 6) if compress else raw, None)

def dec(key: bytes, blob: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], None)

# ---------------------------------------------------------------- Zwischenspeicher
def restore_state(pw: str):
    WORK.mkdir(exist_ok=True)
    if not STATE.exists():
        log("Kein Zwischenspeicher vorhanden – erster Lauf, alles wird geladen.")
        return
    blob = STATE.read_bytes()
    salt, body = blob[:16], blob[16:]
    try:
        tar = dec(derive(pw, salt), body)
    except Exception:
        log("Zwischenspeicher passt nicht zum Passwort (geändert?) – wird neu aufgebaut.")
        return
    with tarfile.open(fileobj=io.BytesIO(tar), mode="r:gz") as t:
        t.extractall(WORK, filter="data") if sys.version_info >= (3, 12) else t.extractall(WORK)
    log("Zwischenspeicher wiederhergestellt.")

def save_state(pw: str):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name in ("cache", ".garminconnect", "site_salt.bin"):
            p = WORK / name
            if p.exists(): t.add(p, arcname=name)
    salt = os.urandom(16)
    STATE.write_bytes(salt + enc(derive(pw, salt), buf.getvalue(), compress=False))
    log(f"Zwischenspeicher verschlüsselt gesichert ({STATE.stat().st_size // 1024} KB).")

# ---------------------------------------------------------------- Anmeldung
TOKEN_NAMES = ("garmin_tokens.json", "oauth1_token.json", "oauth2_token.json")

def _token_files(raw: str) -> dict:
    """Erkennt die üblichen Formate für GARMIN_TOKENS und liefert {Dateiname: Inhalt}.
      a) Ausgabe von tools/garmin_tokens_fuer_github.bat: Base64 von {"<datei>.json": "<inhalt>", ...}
      b) dasselbe als reines JSON
      c) Inhalt einer einzelnen Token-Datei, roh oder Base64:
         - neues Format (garminconnect ≥ 0.3): {"di_token", "di_refresh_token", "di_client_id"} → garmin_tokens.json
         - altes garth-Format: oauth1_token.json / oauth2_token.json
      d) garth.dumps(): Base64 einer Liste [oauth1, oauth2]"""
    raw = raw.strip().strip('"').strip("'")
    cands = []
    try: cands.append(json.loads(raw))
    except Exception: pass
    for pad in ("", "=", "=="):
        try:
            cands.append(json.loads(base64.b64decode(raw + pad, validate=False).decode("utf-8")))
            break
        except Exception:
            continue
    def kind(d):
        if not isinstance(d, dict): return None
        if "di_token" in d or "di_refresh_token" in d: return "garmin_tokens.json"
        if "oauth_token" in d and "oauth_token_secret" in d: return "oauth1_token.json"
        if "access_token" in d and "refresh_token" in d: return "oauth2_token.json"
        return None
    for c in cands:
        if isinstance(c, dict) and c and all(str(k).endswith(".json") for k in c):
            return {Path(str(k)).name: (v if isinstance(v, str) else json.dumps(v)) for k, v in c.items()}
        if isinstance(c, list) and len(c) == 2 and all(isinstance(x, dict) for x in c):
            return {"oauth1_token.json": json.dumps(c[0]), "oauth2_token.json": json.dumps(c[1])}
        if kind(c):
            return {kind(c): json.dumps(c)}
    return {}

def _describe(raw: str) -> str:
    """Beschreibt den Aufbau des Secrets ohne Werte preiszugeben (für die Fehlersuche)."""
    raw = raw.strip()
    for label, txt in (("JSON", raw), ("Base64→JSON", None)):
        try:
            if txt is None: txt = base64.b64decode(raw + "==", validate=False).decode("utf-8")
            d = json.loads(txt)
            if isinstance(d, dict): return f"{label}-Objekt mit Feldern {sorted(d)[:8]}"
            return f"{label} vom Typ {type(d).__name__}"
        except Exception:
            continue
    return f"kein JSON/Base64 erkennbar (Länge {len(raw)} Zeichen)"

def _single_value(raw: str):
    """Ein einzelner Wert aus garmin_tokens.json? Liefert (Feldname, Wert) oder None."""
    v = raw.strip().strip('"').strip("'").strip(",").strip()
    if v.count(".") == 2 and v.startswith("eyJ"):                       # JWT → Zugangsschlüssel
        return ("di_token", v)
    try:
        d = json.loads(base64.b64decode(v + "==", validate=False).decode("utf-8"))
        if isinstance(d, dict) and "refreshTokenValue" in d:            # Base64 {garminGuid, refreshTokenValue}
            return ("di_refresh_token", v)
    except Exception:
        pass
    if 3 <= len(v) <= 200 and " " not in v and "{" not in v:            # kurzer Bezeichner → Client-ID
        return ("di_client_id", v)
    return None

def prepare_tokens() -> Path:
    tok = WORK / ".garminconnect"
    if tok.exists() and any(tok.glob("*.json")):
        return tok
    files, di = {}, {}
    raw = os.environ.get("GARMIN_TOKENS", "")
    if raw.strip():
        files = _token_files(raw)
        if not files:
            sv = _single_value(raw)
            if sv: di[sv[0]] = sv[1]
            else:
                log(f"GARMIN_TOKENS hat ein unbekanntes Format: {_describe(raw)}.")
    # Einzelne Secrets (überschreiben bzw. ergänzen)
    for env, key in (("GARMIN_DI_TOKEN", "di_token"), ("GARMIN_DI_REFRESH_TOKEN", "di_refresh_token"), ("GARMIN_DI_CLIENT_ID", "di_client_id")):
        v = os.environ.get(env, "").strip().strip('"').strip("'").strip(",").strip()
        if v: di[key] = v
    if di:
        base = {}
        if "garmin_tokens.json" in files:
            try: base = json.loads(files["garmin_tokens.json"])
            except Exception: base = {}
        base.update(di)
        missing = [k for k in ("di_token", "di_refresh_token", "di_client_id") if not base.get(k)]
        if missing:
            log(f"Für die Garmin-Anmeldung fehlen noch: {', '.join(missing)}. "
                "Entweder die ganze Datei garmin_tokens.json als GARMIN_TOKENS einfügen "
                "oder die Secrets GARMIN_DI_TOKEN, GARMIN_DI_REFRESH_TOKEN und GARMIN_DI_CLIENT_ID anlegen.")
        files["garmin_tokens.json"] = json.dumps(base)
    if files:
        tok.mkdir(parents=True, exist_ok=True)
        for name, content in files.items(): (tok / name).write_text(content, "utf-8")
        have = sorted(k for k in ("di_token", "di_refresh_token", "di_client_id") if di.get(k) or (k in json.loads(files.get("garmin_tokens.json", "{}") or "{}")))
        log(f"Tokens übernommen: {', '.join(sorted(files))}" + (f" (Felder: {', '.join(have)})" if have else ""))
    return tok

def login(tok: Path):
    try:
        if not (tok.exists() and any(tok.glob("*.json"))):
            raise gx.LoginError("keine Tokens vorhanden")
        return gx.login(tok, interactive=False)
    except gx.LoginError as e:
        email, pw = os.environ.get("GARMIN_EMAIL", ""), os.environ.get("GARMIN_PASSWORD", "")
        if not (email and pw):
            raise SystemExit("Garmin-Anmeldung fehlgeschlagen: Die Tokens aus GARMIN_TOKENS sind ungültig oder unvollständig, "
                             "und GARMIN_EMAIL/GARMIN_PASSWORD sind nicht gesetzt.\n"
                             "Lösung: tools/garmin_tokens_fuer_github.bat ausführen und den Text als GARMIN_TOKENS neu einfügen "
                             "oder GARMIN_EMAIL und GARMIN_PASSWORD als Secrets anlegen.")
        log("Anmeldung mit GARMIN_EMAIL/GARMIN_PASSWORD …")
        from garminconnect import Garmin
        def no_mfa():
            raise SystemExit("Garmin verlangt einen Zwei-Faktor-Code. Im Workflow kann er nicht eingegeben werden.\n"
                             "Bitte das Secret GARMIN_TOKENS mit tools/garmin_tokens_fuer_github.bat erzeugen.")
        try:
            g = Garmin(email, pw, prompt_mfa=no_mfa)
        except TypeError:                                   # ältere/neuere Signatur ohne prompt_mfa
            g = Garmin(email, pw)
        try:
            g.login()
        except SystemExit:
            raise
        except Exception as e:
            raise SystemExit(f"Garmin-Anmeldung mit E-Mail/Passwort fehlgeschlagen: {e}\n"
                             "Bitte GARMIN_EMAIL und GARMIN_PASSWORD prüfen. Verlangt Garmin einen Bestätigungscode, "
                             "geht es nur über GARMIN_TOKENS.")
        log("Anmeldung mit E-Mail/Passwort erfolgreich.")
        tok.mkdir(parents=True, exist_ok=True)
        for dump in (lambda: g.garth.dump(str(tok)), lambda: g.client.dump(str(tok)), lambda: g.dump(str(tok))):
            try: dump(); break
            except Exception: continue
        return g

# ---------------------------------------------------------------- Seite bauen
def main():
    pw = os.environ.get("DASHBOARD_PASSWORD", "")
    if len(pw) < 8:
        raise SystemExit("Secret DASHBOARD_PASSWORD fehlt oder ist kürzer als 8 Zeichen – ohne Verschlüsselung wird nichts veröffentlicht.")
    restore_state(pw)
    tok = prepare_tokens()
    g = login(tok)
    gx.login = lambda *a, **k: g                     # run_export nutzt dieselbe Sitzung
    data = gx.run_export(str(tok), YEARS, WORK, full=os.environ.get("FULL") == "1", interactive=False)
    acts = data.get("activities") or []

    # Detailverläufe nachladen (neueste zuerst, begrenzt pro Lauf)
    dd = WORK / "cache" / "details"; dd.mkdir(parents=True, exist_ok=True)
    def fresh(aid):
        f = dd / f"{aid}.json"
        if not f.exists(): return False
        try: return json.loads(f.read_text("utf-8")).get("v") == gx.DETAIL_VERSION
        except Exception: return False
    todo = [a for a in sorted(acts, key=lambda x: (x["d"], x.get("time", "")), reverse=True) if a.get("id") and not fresh(a["id"])]
    log(f"Detailverläufe: {len(acts) - len(todo)} vorhanden, {len(todo)} fehlen, lade bis zu {MAX_NEW_DETAILS} …")
    for i, a in enumerate(todo[:MAX_NEW_DETAILS]):
        try:
            (dd / f"{a['id']}.json").unlink(missing_ok=True)
            gx.activity_detail(g, a["id"], dd)
        except Exception as e:
            log(f"  {a['id']}: {str(e)[:100]}")
        if i and i % 50 == 0: log(f"  {i} …")

    # Verschlüsseln und Seite schreiben
    sf = WORK / "site_salt.bin"
    if not sf.exists(): sf.write_bytes(os.urandom(16))
    salt = sf.read_bytes(); key = derive(pw, salt)
    shutil.rmtree(SITE, ignore_errors=True); (SITE / "details").mkdir(parents=True)
    shutil.copy(ROOT / "index.html", SITE / "index.html")
    (SITE / ".nojekyll").write_text("")
    def put(path: Path, obj):
        path.write_bytes(enc(key, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")))
    data_only = {k: v for k, v in data.items() if k != "activities"}
    put(SITE / "data.enc", data_only)
    put(SITE / "activities.enc", {"generated_at": data["meta"].get("generated_at"), "activities": acts})
    n = 0
    for f in dd.glob("*.json"):
        (SITE / "details" / (f.stem + ".enc")).write_bytes(enc(key, f.read_bytes())); n += 1
    check = enc(key, b"garmin-dashboard-ok", compress=False)
    (SITE / "site.json").write_text(json.dumps({
        "encrypted": True, "kdf": "PBKDF2-SHA256", "iterations": ITER, "salt": base64.b64encode(salt).decode(),
        "check": base64.b64encode(check).decode(), "generated_at": data["meta"].get("generated_at"),
        "details": n, "activities": len(acts)}), "utf-8")
    log(f"Seite gebaut: {len(data_only['series'])} Kennlinien, {len(acts)} Aktivitäten, {n} Detailverläufe.")
    save_state(pw)

if __name__ == "__main__":
    main()
