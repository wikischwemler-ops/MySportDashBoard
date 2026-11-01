"""Prüft Branch-Namen gegen .githooks/branch-rules.json: neue Branches nur als <Windows-Benutzer>/name.

Als pre-push-Hook: liest die Git-Zeilen von stdin, Exitcode 1 bei unerlaubtem neuem Branch.
  --name NAME   einen Namen prüfen
  --ruleset     GitHub-Ruleset (JSON) aus den Regeln ausgeben
"""
import json, os, re, sys
from pathlib import Path

RULES = json.loads((Path(__file__).parent / "branch-rules.json").read_text("utf-8"))
USERS = [u.lower() for u in RULES["benutzer"]]
ME = (os.environ.get("USERNAME") or os.environ.get("USER") or "").lower()
ZERO = "0" * 40


def ok(name):
    if name in RULES["erlaubt"]:
        return True
    u, sep, rest = name.partition("/")
    return bool(sep) and u == ME and re.match(RULES["name_muster"], rest) is not None


def suggest(name):
    low = re.sub(r"[^a-z0-9._/-]+", "-", name.lower()).strip("-/")
    if low.startswith(ME + "/"):
        low = low[len(ME) + 1:]
    return f"{ME}/{low.replace('/', '-')}"


def report(name):
    tip = suggest(name)
    print(f"""
Push abgelehnt: Branch-Name "{name}" ist nicht erlaubt.
  Neue Branches nur als <Windows-Benutzer>/name, bei dir: {ME}/name
  Name: Kleinbuchstaben, Ziffern, Punkt, Bindestrich, Unterstrich, kein weiterer "/".
  Regeln: .githooks/branch-rules.json
  Vorschlag:  git branch -m "{name}" "{tip}"
              git push -u origin "{tip}"
""", file=sys.stderr)


def warn_unknown():
    if ME not in USERS:
        print(f'\nHinweis: "{ME}" fehlt in "benutzer" in .githooks/branch-rules.json. GitHub lehnt den Branch '
              f'sonst ab: dort eintragen, Ruleset neu erzeugen (--ruleset) und auf GitHub ersetzen.\n', file=sys.stderr)


def ruleset():
    exclude = [f"refs/heads/{b}" for b in RULES["erlaubt"]] + [f"refs/heads/{u}/*" for u in USERS]
    return {"name": "Branch-Namen", "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": ["~ALL"], "exclude": exclude}},
            "rules": [{"type": "creation"}], "bypass_actors": []}


def main(argv):
    if "--ruleset" in argv:
        print(json.dumps(ruleset(), ensure_ascii=False, indent=2))
        return 0
    if not ME:
        print("pre-push: Windows-Benutzer unbekannt (USERNAME fehlt), Branch-Namen werden nicht geprüft.", file=sys.stderr)
        return 0
    if "--name" in argv:
        name = argv[argv.index("--name") + 1]
        if ok(name):
            print(f'"{name}" ist erlaubt.')
            warn_unknown()
            return 0
        report(name)
        return 1
    fail = 0
    for line in sys.stdin:
        p = line.split()
        # nur neu angelegte Branches prüfen (wie das GitHub-Ruleset); Löschen und Aktualisieren bleiben erlaubt
        if len(p) != 4 or not p[2].startswith("refs/heads/") or p[1] == ZERO or p[3] != ZERO:
            continue
        name = p[2][len("refs/heads/"):]
        if not ok(name):
            report(name)
            fail = 1
        else:
            warn_unknown()
    return fail


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
