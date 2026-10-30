#!/usr/bin/env python3
"""
Garmin Dashboard – Export
=========================
Meldet sich mit den gespeicherten Garmin-Tokens an (Standard: %USERPROFILE%\\.garminconnect,
dieselben Tokens wie 'garmin-mcp-auth'), holt die letzten 4 Jahre und schreibt
data.json (Kennlinien) und activities.json (Einzelaktivitäten), jeweils + .js für den Offline-Start,\nneben dieses Skript.

Ein lokaler Zwischenspeicher (cache/) sorgt dafür, dass nach dem ersten Lauf nur noch
neue Tage abgefragt werden.

Aufruf:
    python garmin_export.py                 # normales Update
    python garmin_export.py --years 4       # Zeitraum
    python garmin_export.py --tokens C:\\Users\\HP840G6\\.garminconnect
    python garmin_export.py --full          # Cache ignorieren, alles neu holen
"""
from __future__ import annotations
import argparse, json, os, sys, time, datetime as dt
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
DEFAULT_TOKENS = Path(os.environ.get("GARMINTOKENS", Path.home() / ".garminconnect"))
FINAL_AFTER_DAYS = 3          # ältere Tage gelten als abgeschlossen und werden nicht neu geladen
PAUSE = 0.25                  # Sekunden zwischen API-Aufrufen (schont das Rate-Limit)

def log(*a):
    print(time.strftime("%H:%M:%S") + " " + " ".join(str(x) for x in a), flush=True)

# --------------------------------------------------------------------------- Login
class LoginError(Exception):
    pass

def app_dir() -> Path:
    """Ordner des Programms (auch als .exe)."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else HERE

def load_config() -> dict:
    try:
        return json.loads((app_dir() / "config.json").read_text("utf-8"))
    except Exception:
        return {}

def resolve_tokens(cli: str | None = None) -> Path:
    """Reihenfolge: --tokens, config.json 'tokens', .garminconnect neben dem Programm, ~/.garminconnect."""
    cands = [cli, load_config().get("tokens"), str(app_dir() / ".garminconnect"), str(DEFAULT_TOKENS)]
    for c in cands:
        if c:
            p = Path(os.path.expandvars(c)).expanduser()
            if p.exists() and any(p.glob("*.json")):
                return p
    return Path(os.path.expandvars(cands[0] or cands[1] or str(DEFAULT_TOKENS))).expanduser()

def login(tokenstore: Path, interactive: bool = True):
    try:
        from garminconnect import Garmin
    except ImportError:
        raise LoginError("Paket fehlt: bitte  'pip install garminconnect'  ausführen.")
    g = Garmin()
    try:
        if not (tokenstore.exists() and any(tokenstore.glob("*.json"))):
            raise FileNotFoundError(str(tokenstore))
        g.login(str(tokenstore))
    except Exception as e:
        if not interactive:
            raise LoginError(f"Keine gültigen Tokens in {tokenstore} ({e}). Programm einmal im Konsolenfenster starten und anmelden.")
        log(f"Keine gültigen Tokens in {tokenstore} – einmalige Anmeldung bei Garmin Connect:")
        import getpass
        email = input("  E-Mail: ").strip()
        pw = getpass.getpass("  Passwort (wird nicht gespeichert): ")
        g = Garmin(email, pw, prompt_mfa=lambda: input("  Code aus der Zwei-Faktor-Mail/App: ").strip())
        try:
            g.login()
        except Exception as e2:
            raise LoginError(f"Anmeldung fehlgeschlagen: {e2}")
        tokenstore.mkdir(parents=True, exist_ok=True)
    # aufgefrischte Tokens zurückschreiben, damit die Verbindung dauerhaft bleibt
    try:
        g.garth.dump(str(tokenstore))
    except Exception:
        pass
    log("Angemeldet als", getattr(g, "display_name", None) or getattr(g, "full_name", "?"))
    return g

# --------------------------------------------------------------------------- Cache
class Cache:
    def __init__(self, name):
        CACHE.mkdir(exist_ok=True)
        self.path = CACHE / f"{name}.json"
        try:
            self.d = json.loads(self.path.read_text("utf-8"))
        except Exception:
            self.d = {}
        self.dirty = 0
    def has(self, k): return k in self.d
    def get(self, k): return self.d.get(k)
    def put(self, k, v):
        self.d[k] = v; self.dirty += 1
        if self.dirty >= 25: self.save()
    def save(self):
        if self.dirty:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d, separators=(",", ":")), "utf-8")
            tmp.replace(self.path); self.dirty = 0

def call(fn, *a, retries=4, **kw):
    """API-Aufruf mit Pause und Wiederholung bei Rate-Limit/Netzfehlern."""
    for i in range(retries):
        try:
            r = fn(*a, **kw); time.sleep(PAUSE); return r
        except Exception as e:
            msg = str(e)
            if "429" in msg or "Too Many" in msg:
                w = 30 * (i + 1); log(f"Rate-Limit, warte {w}s …"); time.sleep(w); continue
            if "404" in msg or "204" in msg or "No Content" in msg:
                return None
            if i == retries - 1:
                log(f"  übersprungen ({fn.__name__}): {msg[:120]}"); return None
            time.sleep(3 * (i + 1))
    return None

def dig(d, *path, default=None):
    for p in path:
        if d is None: return default
        if isinstance(d, dict): d = d.get(p)
        elif isinstance(d, list) and isinstance(p, int) and -len(d) <= p < len(d): d = d[p]
        else: return default
    return default if d is None else d

def days(a: dt.date, b: dt.date, step=1):
    while a <= b:
        yield a; a += dt.timedelta(days=step)

# --------------------------------------------------------------------------- Abruf
def fetch_activities(g, start, end, full):
    c = Cache("activities")
    acts = {} if full else dict(c.d)
    for k, v in acts.items():          # ältere Cache-Einträge ohne ID ergänzen
        if k.isdigit(): v.setdefault("id", int(k))
    # vollständige Jahre aus dem Cache, aktuelle 30 Tage immer neu
    if acts and any("name" not in v for v in acts.values()):
        log("Ältere Aktivitätsdaten ohne Namen gefunden – lade alle Aktivitäten einmal neu.")
        acts = {}
    have_until = max((v["d"] for v in acts.values()), default=None)
    have_from = min((v["d"] for v in acts.values()), default=None)
    fetch_from = start if (full or not have_until) else max(start, dt.date.fromisoformat(have_until) - dt.timedelta(days=30))
    spans = [(fetch_from, end)]
    if have_from and fetch_from > start and have_from > start.isoformat():   # Zeitraum wurde nach vorne erweitert
        spans.insert(0, (start, dt.date.fromisoformat(have_from)))
    for span_start, span_end in spans:
        log(f"Aktivitäten {span_start} bis {span_end} …")
        chunk_start = span_start
        while chunk_start <= span_end:
            chunk_end = min(span_end, chunk_start + dt.timedelta(days=180))
            r = call(g.get_activities_by_date, chunk_start.isoformat(), chunk_end.isoformat()) or []
            for a in r:
                rec = slim_activity(a)
                if rec: acts[str(a.get("activityId"))] = rec
            log(f"  {chunk_start} – {chunk_end}: {len(r)}")
            chunk_start = chunk_end + dt.timedelta(days=1)
    c.d = acts; c.dirty = 1; c.save()
    return [a for a in acts.values() if a["d"] >= start.isoformat()]

def slim_activity(a):
    t = (dig(a, "activityType", "typeKey") or "").lower()
    d = (a.get("startTimeLocal") or "")[:10]
    if not d: return None
    return {
        "id": a.get("activityId"), "name": a.get("activityName") or "",
        "time": (a.get("startTimeLocal") or "")[11:16],
        "cal": a.get("calories"), "maxhr": a.get("maxHR"), "te": a.get("aerobicTrainingEffect"),
        "d": d, "t": t,
        "dist": a.get("distance") or 0,                       # m
        "dur": a.get("duration") or 0,                        # s
        "mov": a.get("movingDuration") or a.get("duration") or 0,
        "elev": a.get("elevationGain") or 0,
        "hr": a.get("averageHR"), "cad": a.get("averageRunningCadenceInStepsPerMinute"),
        "gct": a.get("avgGroundContactTime"), "pwr": a.get("avgPower"), "np": a.get("normPower"),
        "swolf": a.get("averageSwolf"), "spl": a.get("avgStrokes") or a.get("averageStrokes"),
        "vo2": a.get("vO2MaxValue"), "event": dig(a, "eventType", "typeKey"),
    }

def fetch_daily(g, start, end, full):
    """Tageswerte: Zusammenfassung + Schlaf (Ruhepuls, Stress, Body Battery, Schritte, SpO2, HRV, Schlaf)."""
    c = Cache("daily")
    if full: c.d = {}
    limit = (dt.date.today() - dt.timedelta(days=FINAL_AFTER_DAYS)).isoformat()
    todo = [d for d in days(start, end) if not (c.has(d.isoformat()) and d.isoformat() < limit)]
    log(f"Tageswerte: {len(todo)} Tage zu laden (erstes Mal dauert das etwas) …")
    for i, d in enumerate(todo):
        k = d.isoformat()
        s = call(g.get_user_summary, k) or {}
        sl = call(g.get_sleep_data, k) or {}
        dto = sl.get("dailySleepDTO") or {}
        c.put(k, {
            "rhr": s.get("restingHeartRate") or sl.get("restingHeartRate"),
            "stress": s.get("averageStressLevel") if (s.get("averageStressLevel") or -1) >= 0 else None,
            "bb": s.get("bodyBatteryHighestValue"),
            "steps": s.get("totalSteps"),
            "spo2": s.get("averageSpo2"),
            "resp": dto.get("averageRespirationValue") or s.get("avgWakingRespirationValue"),
            "sleep": (dto.get("sleepTimeSeconds") or 0) / 3600 or None,
            "sscore": dig(dto, "sleepScores", "overall", "value"),
            "hrv": sl.get("avgOvernightHrv"),
            "im": (s.get("moderateIntensityMinutes") or 0) + 2 * (s.get("vigorousIntensityMinutes") or 0),
        })
        if i % 50 == 0 and i: log(f"  {i}/{len(todo)} ({k})")
    c.save()
    return c.d

def fetch_weekly(g, start, end, full):
    """Wöchentliche Stichprobe: VO2max, Trainingslast, Load-Fokus, Trainingsstatus, Fitnessalter."""
    c = Cache("weekly")
    if full: c.d = {}
    limit = (dt.date.today() - dt.timedelta(days=FINAL_AFTER_DAYS)).isoformat()
    first = start + dt.timedelta(days=(6 - start.weekday()))     # Sonntage
    # neu laden: fehlende/aktuelle Wochen sowie ältere Einträge ohne Load-Fokus/Trainingsstatus
    todo = [d for d in days(first, end, 7)
            if not (c.has(d.isoformat()) and d.isoformat() < limit and "status" in (c.get(d.isoformat()) or {}))]
    if end.weekday() != 6: todo.append(end)
    log(f"Wochenwerte: {len(todo)} Stichtage …")
    for d in todo:
        k = d.isoformat()
        ts = call(g.get_training_status, k) or {}
        vo = ts.get("mostRecentVO2Max") or {}
        load, st = None, {}
        for dev in (dig(ts, "mostRecentTrainingStatus", "latestTrainingStatusData") or {}).values():
            if not isinstance(dev, dict): continue
            load = dev.get("acuteTrainingLoadDTO") or load
            if dev.get("trainingStatusFeedbackPhrase") and (dev.get("primaryTrainingDevice") or not st): st = dev
        lb = {}
        for dev in (dig(ts, "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap") or {}).values():
            if isinstance(dev, dict) and dev.get("monthlyLoadAerobicLow") is not None and (dev.get("primaryTrainingDevice") or not lb): lb = dev
        old = c.get(k) or {}
        fa = {"fitnessAge": old["fage"]} if old.get("fage") else (call(g.get_fitnessage_data, k) or {})
        r1 = lambda v: None if v is None else round(v, 1)
        c.put(k, {
            "status": st.get("trainingStatusFeedbackPhrase"), "status_code": st.get("trainingStatus"),
            "lf_low": r1(lb.get("monthlyLoadAerobicLow")), "lf_high": r1(lb.get("monthlyLoadAerobicHigh")), "lf_ana": r1(lb.get("monthlyLoadAnaerobic")),
            "lf_low_min": lb.get("monthlyLoadAerobicLowTargetMin"), "lf_low_max": lb.get("monthlyLoadAerobicLowTargetMax"),
            "lf_high_min": lb.get("monthlyLoadAerobicHighTargetMin"), "lf_high_max": lb.get("monthlyLoadAerobicHighTargetMax"),
            "lf_ana_min": lb.get("monthlyLoadAnaerobicTargetMin"), "lf_ana_max": lb.get("monthlyLoadAnaerobicTargetMax"),
            "lf_fb": lb.get("trainingBalanceFeedbackPhrase"),
            "vo2run": dig(vo, "generic", "vo2MaxPreciseValue") or dig(vo, "generic", "vo2MaxValue"),
            "vo2bike": dig(vo, "cycling", "vo2MaxPreciseValue") or dig(vo, "cycling", "vo2MaxValue"),
            "atl": dig(load, "dailyTrainingLoadAcute"), "ctl": dig(load, "dailyTrainingLoadChronic"),
            "acwr": dig(load, "dailyAcuteChronicWorkloadRatio"),
            "fage": fa.get("fitnessAge"),
        })
    c.save()
    return c.d

RANGE_KEYS = ("weight", "fat", "bmi", "fatkg", "lean", "muscle", "bone", "water", "endur", "hill", "pred", "lthr", "ltpace", "ltpwr")
def fetch_ranges(g, start, end):
    """Bereichsabfragen: Gewicht, Ausdauerwert, Hill Score, Prognosen, Laktatschwelle."""
    out = {k: {} for k in RANGE_KEYS}
    # Zeiträume mit falschen Waagen-/Profileinstellungen (config.json "bodycomp_exclude": [["von", "bis"], …]):
    # Gewicht bleibt, Körperzusammensetzung wird verworfen
    excl = load_config().get("bodycomp_exclude") or []
    for a in days(start, end, 120):
        b = min(end, a + dt.timedelta(days=119))
        A, B = a.isoformat(), b.isoformat()
        bc = call(g.get_body_composition, A, B) or {}
        # CHANGE_LOG und USER_SETTING sind Profilangaben, keine Wiegungen
        L = [w for w in bc.get("dateWeightList") or [] if w.get("sourceType") not in ("CHANGE_LOG", "USER_SETTING")]
        ok = [w for w in L if w.get("bodyFat") and not any(x <= (w.get("calendarDate") or "") <= y for x, y in excl)]
        # Einzelne Fehlmessungen (z. B. nasse Füße): Körperfett weit weg vom Median des Fensters → Zusammensetzung verwerfen
        fats = sorted(w["bodyFat"] for w in ok)
        med = fats[len(fats) // 2] if fats else None
        for w in L:
            d = w.get("calendarDate") or ""
            if w.get("weight"): out["weight"][d] = w["weight"] / 1000
            if w.get("bmi"): out["bmi"][d] = w["bmi"]
            if w not in ok or abs(w["bodyFat"] - med) > 4: continue
            out["fat"][d] = w["bodyFat"]
            if w.get("weight"):
                out["fatkg"][d] = w["weight"] / 1000 * w["bodyFat"] / 100
                out["lean"][d] = w["weight"] / 1000 - out["fatkg"][d]
            if w.get("muscleMass"): out["muscle"][d] = w["muscleMass"] / 1000
            if w.get("boneMass"): out["bone"][d] = w["boneMass"] / 1000
            if w.get("bodyWater"): out["water"][d] = w["bodyWater"]
        es = call(g.get_endurance_score, A, B) or {}
        for d, v in (es.get("groupMap") or {}).items():
            val = v.get("groupAverage") if isinstance(v, dict) else None
            if val: out["endur"][d] = val
        hs = call(g.get_hill_score, A, B) or {}
        for v in hs.get("hillScoreDTOList") or []:
            if v.get("overallScore"): out["hill"][v.get("calendarDate")] = v["overallScore"]
    # Prognosen (monatlich)
    try:
        pr = call(g.get_race_predictions, start.isoformat(), end.isoformat(), "monthly") or []
    except TypeError:
        pr = []
    for p in pr if isinstance(pr, list) else []:
        d = p.get("calendarDate") or p.get("fromCalendarDate") or (f"{p.get('year')}-{int(p.get('month', 1)):02d}-15" if p.get("year") else None)
        if d: out["pred"][d[:10]] = {k: p.get(k) for k in ("time5K", "time10K", "timeHalfMarathon", "timeMarathon")}
    # Laktatschwelle (Garmin liefert Herzfrequenz, Pace und Leistung als Verlauf; je Jahr abfragen)
    def lt_items(obj, *keys):
        for k in keys:
            v = obj.get(k) if isinstance(obj, dict) else None
            if isinstance(v, list): return v
        return []
    def lt_date(x): return str(x.get("from") or x.get("calendarDate") or x.get("date") or "")[:10]
    def lt_val(x): return x.get("value") if x.get("value") is not None else x.get("speed_mps") or x.get("heart_rate_bpm") or x.get("power_watts")
    for a in days(start, end, 365):
        b = min(end, a + dt.timedelta(days=364))
        lt = None
        for agg in ("daily", "weekly", None):
            try:
                kw = dict(latest=False, start_date=a.isoformat(), end_date=b.isoformat())
                if agg: kw["aggregation"] = agg
                lt = g.get_lactate_threshold(**kw); time.sleep(PAUSE)
                break
            except TypeError:
                continue
            except Exception as e:
                log(f"  Laktatschwelle {a.year}: {str(e)[:100]}"); break
        if not isinstance(lt, dict): continue
        for x in lt_items(lt, "heart_rate", "heartRate", "heart_rate_history"):
            if (x.get("series") or "running") == "running" and lt_val(x): out["lthr"][lt_date(x)] = lt_val(x)
        for x in lt_items(lt, "speed", "speed_history"):
            v = lt_val(x)
            if (x.get("series") or "running") == "running" and v:
                mps = v * 10 if v < 1 else v            # Garmin liefert teils 1/10 m/s
                out["ltpace"][lt_date(x)] = 1000 / mps
        for x in lt_items(lt, "power", "power_history"):
            if (x.get("series") or "running") == "running" and lt_val(x): out["ltpwr"][lt_date(x)] = lt_val(x)
    return out

# --------------------------------------------------------------------------- Aufbereitung
# Trainingsstatus: Garmin-Phrase (z. B. "PRODUCTIVE_3") → Stufe für die Kennlinie
STATUS_LEVEL = {"DETRAINING": 1, "RECOVERY": 2, "UNPRODUCTIVE": 3, "MAINTAINING": 4, "PRODUCTIVE": 5,
                "PEAKING": 6, "OVERREACHING": 7, "STRAINED": 8}
def status_key(phrase):
    if not phrase: return None
    p = str(phrase).upper()
    return next((k for k in STATUS_LEVEL if p.startswith(k)), None)
RUN = ("running", "trail_running", "treadmill_running", "track_running", "virtual_run", "indoor_running", "ultra_run", "obstacle_run")
BIKE = ("cycling", "road_biking", "mountain_biking", "gravel_cycling", "indoor_cycling", "virtual_ride", "cyclocross", "e_bike_fitness", "e_bike_mountain", "bmx", "recumbent_cycling", "track_cycling")
SWIM = ("lap_swimming", "open_water_swimming", "swimming")
def sport(t):
    if t in RUN or t.endswith("_running") or t == "run": return "run"
    if t in BIKE or "cycling" in t or "biking" in t: return "bike"
    if t in SWIM or "swim" in t: return "swim"
    return "other"

def month_keys(start, end):
    y, m, out = start.year, start.month, []
    while (y, m) <= (end.year, end.month):
        out.append(f"{y}-{m:02d}"); m += 1
        if m == 13: y, m = y + 1, 1
    return out

def wavg(items, key, w="dur"):
    num = sum((a[key] or 0) * (a[w] or 0) for a in items if a.get(key))
    den = sum((a[w] or 0) for a in items if a.get(key))
    return num / den if den else None

def build(acts, daily, weekly, rng, start, end):
    months = month_keys(start, end)
    by = defaultdict(lambda: defaultdict(list))
    for a in acts:
        by[sport(a["t"])][a["d"][:7]].append(a)
    S = {}
    def add(id, group, label, unit, freq, data, fmt="num", agg="sum", better="up", dec=1):
        data = [[k, round(v, dec) if dec else round(v)] for k, v in data if v is not None]
        if any(v for _, v in data):
            S[id] = dict(group=group, label=label, unit=unit, freq=freq, fmt=fmt, agg=agg, better=better, dec=dec, d=data)
    def mser(sp, f): return [(m, f(by[sp].get(m, []))) for m in months]
    km = lambda L: sum(a["dist"] for a in L) / 1000
    hrs = lambda L: sum(a["dur"] for a in L) / 3600
    n = lambda L: len(L)
    elev = lambda L: sum(a["elev"] or 0 for a in L)
    # Laufen
    add("run.km", "run", "Distanz", "km", "month", mser("run", km))
    add("run.h", "run", "Zeit", "h", "month", mser("run", hrs))
    add("run.n", "run", "Aktivitäten", "", "month", mser("run", n), dec=0)
    add("run.elev", "run", "Höhenmeter", "m", "month", mser("run", elev), dec=0)
    add("run.pace", "run", "Ø Pace", "min/km", "month", mser("run", lambda L: sum(a["mov"] for a in L) / km(L) if km(L) > 0.5 else None), fmt="pace", agg="avg", better="down", dec=0)
    add("run.hr", "run", "Ø Herzfrequenz", "bpm", "month", mser("run", lambda L: wavg(L, "hr")), agg="avg", better="down", dec=0)
    add("run.cad", "run", "Ø Kadenz", "spm", "month", mser("run", lambda L: wavg(L, "cad")), agg="avg", dec=0)
    add("run.gct", "run", "Bodenkontaktzeit", "ms", "month", mser("run", lambda L: wavg(L, "gct")), agg="avg", better="down", dec=0)
    add("run.long", "run", "Längster Lauf", "km", "month", mser("run", lambda L: max((a["dist"] for a in L), default=0) / 1000 or None), agg="max")
    add("run.vo2", "run", "VO2max (Aktivität)", "ml/kg/min", "month", mser("run", lambda L: max((a["vo2"] or 0 for a in L), default=0) or None), agg="last", dec=0)
    # Rad
    add("bike.km", "bike", "Distanz", "km", "month", mser("bike", km))
    add("bike.h", "bike", "Zeit", "h", "month", mser("bike", hrs))
    add("bike.n", "bike", "Aktivitäten", "", "month", mser("bike", n), dec=0)
    add("bike.elev", "bike", "Höhenmeter", "m", "month", mser("bike", elev), dec=0)
    add("bike.speed", "bike", "Ø Geschwindigkeit", "km/h", "month", mser("bike", lambda L: (sum(a["dist"] for a in L if a["dist"]) / 1000) / (sum(a["mov"] for a in L if a["dist"]) / 3600) if sum(a["mov"] for a in L if a["dist"]) > 600 else None), agg="avg")
    add("bike.pwr", "bike", "Ø Leistung", "W", "month", mser("bike", lambda L: wavg(L, "pwr")), agg="avg", dec=0)
    add("bike.np", "bike", "Normalized Power", "W", "month", mser("bike", lambda L: wavg(L, "np")), agg="avg", dec=0)
    add("bike.hr", "bike", "Ø Herzfrequenz", "bpm", "month", mser("bike", lambda L: wavg(L, "hr")), agg="avg", better="down", dec=0)
    # Schwimmen
    add("swim.km", "swim", "Distanz", "km", "month", mser("swim", km), dec=2)
    add("swim.h", "swim", "Zeit", "h", "month", mser("swim", hrs))
    add("swim.n", "swim", "Aktivitäten", "", "month", mser("swim", n), dec=0)
    add("swim.pace", "swim", "Ø Pace", "min/100m", "month", mser("swim", lambda L: sum(a["mov"] for a in L) / (km(L) * 10) if km(L) > 0.2 else None), fmt="pace", agg="avg", better="down", dec=0)
    add("swim.swolf", "swim", "Ø SWOLF", "", "month", mser("swim", lambda L: wavg(L, "swolf")), agg="avg", better="down", dec=0)
    add("swim.hr", "swim", "Ø Herzfrequenz", "bpm", "month", mser("swim", lambda L: wavg(L, "hr")), agg="avg", better="down", dec=0)
    # Sonstige
    add("other.h", "other", "Zeit gesamt", "h", "month", mser("other", hrs))
    add("other.n", "other", "Aktivitäten", "", "month", mser("other", n), dec=0)
    add("other.str", "other", "Krafttraining", "h", "month", mser("other", lambda L: hrs([a for a in L if "strength" in a["t"]])))
    add("other.hike", "other", "Wandern/Gehen", "km", "month", mser("other", lambda L: km([a for a in L if a["t"] in ("hiking", "walking", "casual_walking", "speed_walking", "mountaineering")])))
    add("other.yoga", "other", "Yoga/Mobility", "h", "month", mser("other", lambda L: hrs([a for a in L if any(x in a["t"] for x in ("yoga", "pilates", "breath", "mobility", "stretch"))])))
    add("other.ski", "other", "Ski/Langlauf", "h", "month", mser("other", lambda L: hrs([a for a in L if "ski" in a["t"] or "snow" in a["t"]])))

    # Alle Aktivitäten zusammen (wie Garmin-Connect-Berichte)
    allm = defaultdict(list)
    for a in acts: allm[a["d"][:7]].append(a)
    aser = lambda f: [(m, f(allm.get(m, []))) for m in months]
    withd = lambda L: [a for a in L if (a["dist"] or 0) > 100]
    add("all.n", "all", "Aktivitäten", "", "month", aser(n), dec=0)
    add("all.km", "all", "Gesamtdistanz", "km", "month", aser(km))
    add("all.h", "all", "Gesamtzeit", "h", "month", aser(hrs))
    add("all.cal", "all", "Aktivitätskalorien", "kcal", "month", aser(lambda L: sum(a.get("cal") or 0 for a in L) or None), dec=0)
    add("all.hr", "all", "Ø Herzfrequenz", "bpm", "month", aser(lambda L: wavg(L, "hr")), agg="avg", better="down", dec=0)
    add("all.maxhr", "all", "Max. Herzfrequenz", "bpm", "month", aser(lambda L: max((a.get("maxhr") or 0 for a in L), default=0) or None), agg="max", better="none", dec=0)
    add("all.speed", "all", "Ø Geschwindigkeit", "km/h", "month", aser(lambda L: km(withd(L)) / (sum(a["mov"] for a in withd(L)) / 3600) if sum(a["mov"] for a in withd(L)) > 600 else None), agg="avg")
    add("all.pace", "all", "Ø Pace", "min/km", "month", aser(lambda L: sum(a["mov"] for a in withd(L)) / km(withd(L)) if km(withd(L)) > 1 else None), fmt="pace", agg="avg", better="down", dec=0)
    add("all.elev", "all", "Gesamt-Höhenmeter", "m", "month", aser(elev), dec=0)

    # Wochenmittel aus Tageswerten
    def week_of(dstr):
        d = dt.date.fromisoformat(dstr); return (d - dt.timedelta(days=d.weekday())).isoformat()
    wk = defaultdict(lambda: defaultdict(list))
    for d, v in daily.items():
        if not (start.isoformat() <= d <= end.isoformat()) or not v: continue
        for k, x in v.items():
            if x not in (None, 0): wk[k][week_of(d)].append(x)
    def wser(key): return [(w, sum(v) / len(v)) for w, v in sorted(wk[key].items())]
    add("health.rhr", "health", "Ruhepuls", "bpm", "week", wser("rhr"), agg="avg", better="down", dec=0)
    add("health.hrv", "health", "HRV (Nacht Ø)", "ms", "week", wser("hrv"), agg="avg", dec=0)
    add("health.sleep", "health", "Schlafdauer", "h", "week", wser("sleep"), agg="avg")
    add("health.sscore", "health", "Schlafwert", "", "week", wser("sscore"), agg="avg", dec=0)
    add("health.stress", "health", "Ø Stress", "", "week", wser("stress"), agg="avg", better="down", dec=0)
    add("health.bb", "health", "Body Battery max", "", "week", wser("bb"), agg="avg", dec=0)
    add("health.resp", "health", "Atemfrequenz", "/min", "week", wser("resp"), agg="avg", better="down")
    add("health.spo2", "health", "SpO₂", "%", "week", wser("spo2"), agg="avg")
    add("health.steps", "health", "Schritte/Tag", "", "week", wser("steps"), agg="avg", dec=0)
    def rser(key):
        w = defaultdict(list)
        for d, v in rng.get(key, {}).items():
            if d and start.isoformat() <= d[:10] <= end.isoformat(): w[week_of(d[:10])].append(v)
        return [(k, sum(v) / len(v)) for k, v in sorted(w.items())]
    add("health.weight", "health", "Gewicht", "kg", "week", rser("weight"), agg="avg", better="down")
    add("health.fat", "health", "Körperfett", "%", "week", rser("fat"), agg="avg", better="down")
    add("health.fatkg", "health", "Fettmasse", "kg", "week", rser("fatkg"), agg="avg", better="down")
    add("health.lean", "health", "Fettfreie Masse", "kg", "week", rser("lean"), agg="avg")
    add("health.muscle", "health", "Skelettmuskelmasse", "kg", "week", rser("muscle"), agg="avg")
    add("health.bone", "health", "Knochenmasse", "kg", "week", rser("bone"), agg="avg", better="none", dec=2)
    add("health.water", "health", "Körperwasser", "%", "week", rser("water"), agg="avg")
    add("health.bmi", "health", "BMI", "", "week", rser("bmi"), agg="avg", better="none")

    # Fitness & Last
    wkeys = sorted(k for k in weekly if start.isoformat() <= k <= end.isoformat())
    def fser(key): return [(week_of(k), weekly[k].get(key)) for k in wkeys]
    add("fit.vo2run", "fit", "VO2max Laufen", "ml/kg/min", "week", fser("vo2run"), agg="last")
    add("fit.vo2bike", "fit", "VO2max Rad", "ml/kg/min", "week", fser("vo2bike"), agg="last")
    add("fit.age", "fit", "Fitnessalter", "Jahre", "week", fser("fage"), agg="last", better="down")
    add("fit.endur", "fit", "Ausdauerwert", "", "week", rser("endur"), agg="last", dec=0)
    add("fit.hill", "fit", "Hill Score", "", "week", rser("hill"), agg="last", dec=0)
    add("fit.atl", "fit", "Akute Last (7 T)", "", "week", fser("atl"), agg="avg", dec=0)
    add("fit.ctl", "fit", "Chronische Last", "", "week", fser("ctl"), agg="avg", dec=0)
    add("fit.acwr", "fit", "Belastungsverhältnis (ACWR)", "", "week", fser("acwr"), agg="avg", better="none", dec=2)
    add("fit.lf_low", "fit", "Load-Fokus aerob niedrig", "", "week", fser("lf_low"), agg="avg", dec=0)
    add("fit.lf_high", "fit", "Load-Fokus aerob hoch", "", "week", fser("lf_high"), agg="avg", dec=0)
    add("fit.lf_ana", "fit", "Load-Fokus anaerob", "", "week", fser("lf_ana"), agg="avg", dec=0)
    add("fit.status", "fit", "Trainingsstatus", "", "week", [(w, STATUS_LEVEL.get(status_key(v))) for w, v in fser("status")],
        fmt="status", agg="last", better="none", dec=0)
    add("fit.im", "fit", "Intensitätsminuten", "min/Woche", "week", [(w, sum(v)) for w, v in sorted(wk["im"].items())], agg="avg", dec=0)
    add("fit.lthr", "fit", "Laktatschwelle HF", "bpm", "week", rser("lthr"), agg="last", dec=0)
    add("fit.ltpace", "fit", "Laktatschwelle Pace", "min/km", "week", rser("ltpace"), fmt="pace", agg="last", better="down", dec=0)
    add("fit.ltpwr", "fit", "Laktatschwelle Leistung", "W", "week", rser("ltpwr"), agg="last", dec=0)

    # Prognosen
    pm = defaultdict(dict)
    for d, v in rng["pred"].items():
        for k, x in v.items():
            if x: pm[k][d[:7]] = x
    for key, id, lbl in (("time5K", "pred.5k", "Prognose 5 km"), ("time10K", "pred.10k", "Prognose 10 km"),
                         ("timeHalfMarathon", "pred.hm", "Prognose Halbmarathon"), ("timeMarathon", "pred.m", "Prognose Marathon")):
        add(id, "pred", lbl, "h:mm:ss", "month", sorted(pm[key].items()), fmt="time", agg="last", better="down", dec=0)

    act_list = sorted(({"id": a.get("id"), "d": a["d"], "time": a.get("time", ""), "sp": sport(a["t"]), "t": a["t"],
                        "name": a.get("name", ""), "km": round((a["dist"] or 0) / 1000, 2), "dur": round(a["dur"] or 0),
                        "elev": round(a["elev"] or 0), "hr": a.get("hr") and round(a["hr"]), "maxhr": a.get("maxhr"),
                        "pwr": a.get("pwr") and round(a["pwr"]), "cal": a.get("cal") and round(a["cal"]),
                        "te": a.get("te"), "race": a.get("event") == "race"} for a in acts if a.get("id")),
                      key=lambda x: (x["d"], x["time"]))
    extra = {"loadfocus": [[week_of(k)] + [weekly[k].get(x) for x in ("lf_low", "lf_low_min", "lf_low_max", "lf_high", "lf_high_min",
                                     "lf_high_max", "lf_ana", "lf_ana_min", "lf_ana_max", "lf_fb")]
                           for k in wkeys if weekly[k].get("lf_low") is not None],
             "status": [[week_of(k), status_key(weekly[k].get("status")), weekly[k].get("status")] for k in wkeys if status_key(weekly[k].get("status"))]}
    groups = [dict(id="all", label="Alle Aktivitäten", key="all.km"), dict(id="run", label="Laufen", key="run.km"), dict(id="bike", label="Rad", key="bike.km"),
              dict(id="swim", label="Schwimmen", key="swim.km"), dict(id="other", label="Sonstige", key="other.h"),
              dict(id="fit", label="Fitness & Last", key="fit.vo2run"), dict(id="health", label="Gesundheit", key="health.hrv"),
              dict(id="pred", label="Prognosen", key="pred.10k")]
    groups = [g for g in groups if any(s["group"] == g["id"] for s in S.values())]
    return dict(meta=dict(source="garmin", title="Garmin Dashboard", generated=dt.date.today().isoformat(),
                          generated_at=dt.datetime.now().isoformat(timespec="minutes"),
                          **{"from": months[0], "to": months[-1]}, activities=len(acts)),
                groups=groups, series=S, extra=extra, activities=act_list)

# --------------------------------------------------------------------------- Einzelaktivität
DETAIL_VERSION = 3   # erhöhen, wenn sich der Inhalt ändert → alte Cache-Dateien werden neu geladen

def first(d, *keys):
    for k in keys:
        if d.get(k) not in (None, ""): return d[k]
    return None

def _gmt(s):
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "")[:19]).timestamp()
    except Exception: return None

def swim_lengths(out, lap_dtos):
    """Beckenschwimmen: Garmin zeichnet Tempo, Züge und SWOLF pro Bahn auf, nicht sekündlich.
    Daraus werden Treppen-Kennlinien auf der Zeitachse und eine fortlaufende Distanz gebaut."""
    lengths = [x for l in lap_dtos for x in (l.get("lengthDTOs") or [])]
    if not lengths or not lap_dtos: return
    t0 = _gmt(lap_dtos[0].get("startTimeGMT"))
    if t0 is None: return
    L = []
    for x in lengths:
        st, du, di = _gmt(x.get("startTimeGMT")), x.get("duration") or 0, x.get("distance") or 0
        if st is None: continue
        L.append({"a": st - t0, "e": st - t0 + du, "dist": di, "dur": du, "speed": first(x, "averageSpeed"),
                  "hr": first(x, "averageHR"), "strokes": first(x, "totalNumberOfStrokes", "totalStrokes"),
                  "swolf": first(x, "averageSWOLF", "averageSwolf"), "srate": first(x, "averageSwimCadenceInStrokesPerMinute", "averageSwimCadence"),
                  "stroke": first(x, "swimStroke", "stroke")})
    if not L: return
    out["lengths"] = [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()} for x in L if x["dist"]]
    out["swim"] = True
    t = out["t"]; ch = {k: [] for k in ("speed", "strokes", "swolf", "srate")}; dist = []
    j, done = 0, 0.0
    for ti in t:
        while j < len(L) and L[j]["e"] <= ti:
            done += L[j]["dist"]; j += 1
        cur = L[j] if j < len(L) and L[j]["a"] <= ti < L[j]["e"] and L[j]["dist"] else None
        for k in ch: ch[k].append(cur[k] if cur else None)
        frac = (ti - cur["a"]) / cur["dur"] if cur and cur["dur"] else 0
        dist.append(round(done + (cur["dist"] * frac if cur else 0), 1))
    for k, v in ch.items():
        if any(x not in (None, 0) for x in v): out["ch"][k] = v
    if not any(out.get("dist") or []): out["dist"] = dist
METRICS = {  # Garmin-Schlüssel → Kurzname
    "directHeartRate": "hr", "directSpeed": "speed", "directGradeAdjustedSpeed": "gap", "directElevation": "elev",
    "directDoubleCadence": "cad", "directRunCadence": "cad1", "directBikeCadence": "cad", "directFractionalCadence": None,
    "directPower": "pwr", "directGroundContactTime": "gct", "directVerticalOscillation": "vo", "directVerticalRatio": "vr",
    "directStrideLength": "stride", "directGroundContactBalanceLeft": "gcb", "directVerticalSpeed": "vspeed", "directAirTemperature": "temp",
    "directRespirationRate": "resp", "directPerformanceCondition": "perf", "directBodyBattery": "bb",
    "directStamina": "stamina", "directPotentialStamina": None, "directLeftPedalSmoothness": None,
    "directSwimStroke": "strokes", "directStrokeRate": "srate", "directSwolf": "swolf",
}

def activity_detail(g, aid, cache_dir: Path):
    """Verläufe, Runden, HF-Zonen und Strecke einer Aktivität (mit Dateicache)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / f"{aid}.json"
    if f.exists():
        cached = json.loads(f.read_text("utf-8"))
        if cached.get("v") == DETAIL_VERSION:
            return cached
    det = call(g.get_activity_details, aid, 2000, 4000) or {}
    idx = {d.get("metricsIndex"): d.get("key") for d in det.get("metricDescriptors") or []}
    rows = [m.get("metrics") or [] for m in det.get("activityDetailMetrics") or []]
    col = lambda key: [r[i] if i < len(r) else None for r in rows] if (i := next((k for k, v in idx.items() if v == key), None)) is not None else None
    t = col("sumElapsedDuration") or col("sumDuration") or list(range(len(rows)))
    t0 = next((x for x in t if x is not None), 0)
    out = {"v": DETAIL_VERSION, "id": aid, "t": [round((x or 0) - t0, 1) for x in t], "dist": [x and round(x, 1) for x in (col("sumDistance") or [])], "ch": {}}
    for key, short in METRICS.items():
        if not short: continue
        v = col(key)
        if v and any(x not in (None, 0) for x in v):
            if short == "cad1" and "cad" in out["ch"]: continue
            out["ch"]["cad" if short == "cad1" else short] = [None if x is None else round(x, 2) for x in v]
    if "cad" in out["ch"] and col("directRunCadence") and not col("directDoubleCadence"):
        out["ch"]["cad"] = [None if x is None else round(x * 2) for x in out["ch"]["cad"]]  # Einbein → Schritte/min
    poly = dig(det, "geoPolylineDTO", "polyline") or []
    out["route"] = [[round(p["lat"], 5), round(p["lon"], 5)] for p in poly if p.get("lat") and p.get("lon")]
    if not out["route"]:
        la, lo = col("directLatitude"), col("directLongitude")
        if la and lo: out["route"] = [[round(a, 5), round(b, 5)] for a, b in zip(la, lo) if a and b][::2]
    sp = call(g.get_activity_splits, aid) or {}
    lap_dtos = sp.get("lapDTOs") or []
    out["laps"] = [{"dist": l.get("distance"), "dur": l.get("duration"), "hr": l.get("averageHR"), "maxhr": l.get("maxHR"),
                    "speed": l.get("averageSpeed"), "elev": l.get("elevationGain"), "cad": l.get("averageRunCadence") or l.get("averageBikeCadence"),
                    "pwr": l.get("averagePower"), "strokes": first(l, "totalNumberOfStrokes", "totalStrokes"),
                    "swolf": first(l, "averageSWOLF", "averageSwolf"), "srate": first(l, "averageSwimCadenceInStrokesPerMinute", "averageSwimCadence"),
                    "lengths": first(l, "numberOfActiveLengths", "activeLengthCount")} for l in lap_dtos]
    swim_lengths(out, lap_dtos)
    z = call(g.get_activity_hr_in_timezones, aid) or []
    out["zones"] = [{"z": x.get("zoneNumber"), "secs": x.get("secsInZone") or 0, "low": x.get("zoneLowBoundary")} for x in z if isinstance(x, dict)]
    f.write_text(json.dumps(out, separators=(",", ":")), "utf-8")
    return out

# --------------------------------------------------------------------------- main
PLAN_SPORT = {"running": "run", "trail_running": "run", "cycling": "bike", "swimming": "swim", "lap_swimming": "swim"}
STEP_NAME = {"warmup": "Einlaufen", "cooldown": "Auslaufen", "interval": "Belastung", "recovery": "Erholung",
             "rest": "Pause", "other": "Abschnitt", "main": "Hauptteil"}

def _pace(v, swim):
    if not v: return None
    s = (100 if swim else 1000) / v
    return f"{int(s // 60)}:{int(round(s % 60)):02d}"

def plan_step(s, swim):
    """Workout-Schritt (Garmin-DTO) → {t, end, tgt, note}, Wiederholungsblock → {rep, steps}; dazu geschätzte Dauer/Strecke."""
    if s.get("type") == "RepeatGroupDTO":
        n = int(s.get("numberOfIterations") or 1)
        sub = [plan_step(c, swim) for c in s.get("workoutSteps") or []]
        return {"rep": n, "steps": [x[0] for x in sub]}, n * sum(x[1] for x in sub), n * sum(x[2] for x in sub)
    cond, val = dig(s, "endCondition", "conditionTypeKey"), s.get("endConditionValue") or 0
    sec = val if cond == "time" else 0
    m = val if cond == "distance" else 0
    end = ((f"{int(sec // 60)} min" if sec % 60 == 0 else f"{int(sec)} s" if sec < 120 else f"{int(sec // 60)}:{int(sec % 60):02d} min") if cond == "time" else
           (f"{nf_de(m / 1000, 1 if m % 1000 else 0)} km" if m >= 1000 else f"{int(m)} m") if cond == "distance" else
           "bis Lap-Taste" if cond == "lap.button" else "")
    tt, a, b = dig(s, "targetType", "workoutTargetTypeKey"), s.get("targetValueOne"), s.get("targetValueTwo")
    z = s.get("zoneNumber")
    tgt = ""
    if tt == "heart.rate.zone":
        tgt = (f"Z{z} " if z else "") + (f"{int(a)}-{int(b)} bpm" if a and b else "")
    elif tt in ("pace.zone", "speed.zone") and a and b:
        tgt = f"{_pace(max(a, b), swim)}-{_pace(min(a, b), swim)} /{'100 m' if swim else 'km'}"
    elif tt == "power.zone" and a and b:
        tgt = (f"Z{z} " if z else "") + f"{int(a)}-{int(b)} W"
    elif tt == "cadence" and a and b:
        tgt = f"{int(a)}-{int(b)} spm"
    return {"t": STEP_NAME.get(dig(s, "stepType", "stepTypeKey"), "Abschnitt"), "end": end.strip(), "tgt": tgt.strip(),
            "note": (s.get("description") or "").strip()}, sec, m

def nf_de(v, d):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fetch_plan(g, today):
    """Geplante Workouts (mit Schritten, erledigt = mit Aktivität verknüpft) und Wettkampftermine aus dem Garmin-Kalender."""
    a, b = (today.replace(day=1) - dt.timedelta(days=62)).replace(day=1), today + dt.timedelta(days=150)
    items = []
    for s in call(g.get_scheduled_workouts_by_period, a.isoformat(), b.isoformat()) or []:
        w = s.get("workout") or {}
        key = dig(w, "sportType", "sportTypeKey") or ""
        swim = PLAN_SPORT.get(key) == "swim"
        steps, sec, m = [], 0, 0
        for seg in w.get("workoutSegments") or []:
            for st in seg.get("workoutSteps") or []:
                x, ds, dm = plan_step(st, swim); steps.append(x); sec += ds; m += dm
        items.append({"id": s.get("workoutScheduleId"), "d": s.get("calendarDate"), "sp": PLAN_SPORT.get(key, "other"),
                      "name": s.get("newName") or w.get("workoutName") or "Workout", "desc": w.get("description") or "",
                      "dur": w.get("estimatedDurationInSecs") or sec or None, "m": w.get("estimatedDistanceInMeters") or m or None,
                      "aid": s.get("associatedActivityId"), "race": bool(s.get("race")), "steps": steps})
    events, seen = [], set()
    y, mo = a.year, a.month
    while (y, mo) <= (b.year, b.month):
        for c in (call(g.get_scheduled_workouts, y, mo) or {}).get("calendarItems") or []:
            if c.get("itemType") == "event" and (c.get("date"), c.get("title")) not in seen:
                seen.add((c.get("date"), c.get("title")))
                ct = c.get("completionTarget") or {}
                events.append({"d": c.get("date"), "name": c.get("title"), "loc": c.get("location"),
                               "km": round(ct["value"] / 1000, 1) if ct.get("unit") == "meter" and ct.get("value") else None,
                               "primary": bool(c.get("primaryEvent"))})
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    items.sort(key=lambda x: (x["d"] or "", x["id"] or 0)); events.sort(key=lambda x: x["d"] or "")
    return {"from": a.isoformat(), "to": b.isoformat(), "items": items, "events": events}

def run_export(tokens=None, years=4.0, out=None, full=False, no_health=False, interactive=True):
    global CACHE
    out = Path(out or app_dir())
    CACHE = out / "cache"
    end = dt.date.today()
    start = (end - dt.timedelta(days=int(years * 365.25))).replace(day=1)
    if load_config().get("start"):                 # festes Startdatum (z. B. erste Garmin-Aufzeichnung) hat Vorrang vor "years"
        start = dt.date.fromisoformat(load_config()["start"])
    tok = resolve_tokens(tokens)
    log(f"Zeitraum {start} bis {end} · Tokens: {tok}")
    g = login(tok, interactive)
    a = argparse.Namespace(full=full, no_health=no_health, out=str(out))
    acts = fetch_activities(g, start, end, a.full)
    log(f"{len(acts)} Aktivitäten")
    if a.no_health:
        daily, weekly, rng = Cache("daily").d, Cache("weekly").d, {k: {} for k in RANGE_KEYS}
    else:
        daily = fetch_daily(g, start, end, a.full)
        weekly = fetch_weekly(g, start, end, a.full)
        rng = fetch_ranges(g, start, end)
    data = build(acts, daily, weekly, rng, start, end)
    # Körpermaße für die Laufkinematik (Feder-Masse-Modell): letzte Wiegung, sonst Profilgewicht; Größe aus dem Profil
    u = (call(g.get_user_profile) or {}).get("userData") or {}
    w = sorted(rng.get("weight", {}).items())
    kg = w[-1][1] if w else (u.get("weight") or 0) / 1000
    data["meta"]["body"] = {"kg": round(kg, 1) if kg else None, "cm": u.get("height")}
    data["plan"] = fetch_plan(g, end)
    log(f"Trainingsplan: {len(data['plan']['items'])} geplante Workouts, {len(data['plan']['events'])} Wettkämpfe")
    act_list = data.pop("activities")          # Einzelaktivitäten getrennt von den Kennlinien
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    def write(name, var, obj):
        txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        tmp = out / (name + ".tmp"); tmp.write_text(txt, "utf-8"); tmp.replace(out / f"{name}.json")
        (out / f"{name}.js").write_text(f"window.{var}=" + txt + ";", "utf-8")
    write("data", "GARMIN_DATA", data)
    write("activities", "GARMIN_ACTIVITIES", {"generated_at": data["meta"]["generated_at"], "activities": act_list})
    log(f"Fertig: {len(data['series'])} Kennlinien → data.json, {len(act_list)} Aktivitäten → activities.json")
    data["activities"] = act_list
    return data

def main():
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Garmin Connect → data.json für das Dashboard")
    ap.add_argument("--tokens", default=None, help="Token-Ordner (Standard: config.json, ./.garminconnect, ~/.garminconnect)")
    ap.add_argument("--years", type=float, default=cfg.get("years", 4))
    ap.add_argument("--out", default=None)
    ap.add_argument("--full", action="store_true", help="Cache ignorieren und alles neu laden")
    ap.add_argument("--no-health", action="store_true", help="nur Aktivitäten (schnell)")
    a = ap.parse_args()
    try:
        run_export(a.tokens, a.years, a.out, a.full, a.no_health)
    except LoginError as e:
        sys.exit(str(e))

if __name__ == "__main__":
    main()
