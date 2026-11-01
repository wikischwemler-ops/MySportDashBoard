"""Prüft Branch-Namen gegen .githooks/branch-rules.json: neue Branches nur zweistufig als xxx/yyy.

xxx = Präfix (feat, fix, Windows-Benutzer …), yyy = funktionaler Name.
Als pre-push-Hook: liest die Git-Zeilen von stdin, Exitcode 1 bei unerlaubtem neuem Branch.
  --name NAME   einen Namen prüfen
  --ruleset     GitHub-Ruleset (JSON) aus den Regeln ausgeben
"""
import json, os, re, sys
from pathlib import Path

RULES = json.loads((Path(__file__).parent / "branch-rules.json").read_text("utf-8"))
TYPES = [p for p in RULES["praefix_beispiele"] if not p.startswith("<")]
ME = re.sub(r"[^a-z0-9._-]+", "-", (os.environ.get("USERNAME") or os.environ.get("USER") or "").lower())
ZERO = "0" * 40


def ok(name):
    if name in RULES["erlaubt"]:
        return True
    p, sep, rest = name.partition("/")
    return bool(sep) and re.match(RULES["praefix_muster"], p) is not None and re.match(RULES["name_muster"], rest) is not None


def suggest(name):
    low = re.sub(r"[^a-z0-9._/-]+", "-", name.lower()).strip("-/")
    if "/" in low:                                   # zu tief: Rest zusammenziehen
        p, _, rest = low.partition("/")
        return f"{p}/{rest.replace('/', '-')}"
    for t in TYPES:                                  # fix-garmin-tokens -> fix/garmin-tokens
        for sep in ("-", "_", "."):
            if low.startswith(t + sep) and len(low) > len(t) + 1:
                return f"{t}/{low[len(t) + 1:]}"
    return f"{ME or 'feat'}/{low}"


def report(name):
    tip = suggest(name)
    bsp = "\n".join(f"    {p:<20}{d}" for p, d in RULES["praefix_beispiele"].items())
    print(f"""
Push abgelehnt: Branch-Name "{name}" ist nicht erlaubt.
  Neue Branches nur zweistufig: xxx/yyy  (xxx = Präfix, yyy = funktionaler Name)
  Präfix-Beispiele:
{bsp}
  Erlaubte Zeichen: Kleinbuchstaben, Ziffern, Punkt, Bindestrich, Unterstrich; genau ein "/".
  Regeln: .githooks/branch-rules.json
  Vorschlag:  git branch -m "{name}" "{tip}"
              git push -u origin "{tip}"
""", file=sys.stderr)


def ruleset():
    # GitHub-Muster: "*" umfasst keinen "/", also genau zwei Stufen
    exclude = [f"refs/heads/{b}" for b in RULES["erlaubt"]] + ["refs/heads/*/*"]
    return {"name": "Branch-Namen", "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": ["~ALL"], "exclude": exclude}},
            "rules": [{"type": "creation"}], "bypass_actors": []}


def main(argv):
    if "--ruleset" in argv:
        print(json.dumps(ruleset(), ensure_ascii=False, indent=2))
        return 0
    if "--name" in argv:
        name = argv[argv.index("--name") + 1]
        if ok(name):
            print(f'"{name}" ist erlaubt.')
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
    return fail


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
