"""Prüft Branch-Namen gegen .githooks/branch-rules.json.

Als pre-push-Hook: liest die Git-Zeilen von stdin, Exitcode 1 bei unerlaubtem Namen.
  --name NAME   einen Namen prüfen
  --ruleset     GitHub-Ruleset (JSON) aus den Regeln ausgeben
"""
import json, re, sys
from pathlib import Path

RULES = json.loads((Path(__file__).parent / "branch-rules.json").read_text("utf-8"))
TYPES = list(RULES["typen"])
ZERO = "0" * 40


def ok(name):
    if name in RULES["erlaubt"]:
        return True
    t, sep, rest = name.partition("/")
    return bool(sep) and t in TYPES and re.match(RULES["name_muster"], rest) is not None


def suggest(name):
    low = re.sub(r"[^a-z0-9._/-]+", "-", name.lower()).strip("-/")
    for t in TYPES:
        for sep in ("/", "-", "_"):
            if low.startswith(t + sep):
                return f"{t}/{low[len(t) + 1:].replace('/', '-')}"
    return f"{RULES['standard_typ']}/{low.replace('/', '-')}"


def report(name):
    tip = suggest(name)
    typen = "\n".join(f"    {t:<9}{d}" for t, d in RULES["typen"].items())
    print(f"""
Push abgelehnt: Branch-Name "{name}" ist nicht erlaubt.
  Erlaubt ist nur typ/name (Regeln: .githooks/branch-rules.json). Typen:
{typen}
  Name: Kleinbuchstaben, Ziffern, Punkt, Bindestrich, Unterstrich, kein weiterer "/".
  Vorschlag:  git branch -m "{name}" "{tip}"
              git push -u origin "{tip}"
""", file=sys.stderr)


def ruleset():
    exclude = [f"refs/heads/{b}" for b in RULES["erlaubt"]] + [f"refs/heads/{t}/*" for t in TYPES]
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
        if len(p) != 4 or not p[2].startswith("refs/heads/") or p[1] == ZERO:   # nur Branches, Löschen erlaubt
            continue
        name = p[2][len("refs/heads/"):]
        if not ok(name):
            report(name)
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
