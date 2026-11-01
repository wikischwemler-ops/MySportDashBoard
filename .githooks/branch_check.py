"""Checks branch names against .githooks/branch-rules.json: new branches must use two levels, prefix/name.

prefix = feat, fix, userID, ...; name = functional name.
As pre-push hook: reads Git's lines from stdin, exit code 1 for a disallowed new branch.
  --name NAME   check a single name
  --ruleset     print the GitHub ruleset (JSON) derived from the rules
"""
import json, re, sys
from pathlib import Path

RULES = json.loads((Path(__file__).parent / "branch-rules.json").read_text("utf-8"))
ZERO = "0" * 40


def ok(name):
    if name in RULES["allowed"]:
        return True
    p, sep, rest = name.partition("/")
    return bool(sep) and re.match(RULES["prefix_pattern"], p) is not None and re.match(RULES["name_pattern"], rest) is not None


def report(name):
    ex = "\n".join(f"    {p:<18}{d}" for p, d in RULES["prefix_examples"].items())
    print(f"""
Push rejected: branch name "{name}" is not allowed.
  New branches must use two levels: <prefix>/<name>  (prefix = type or userID, name = functional name)
  Prefix examples:
{ex}
  Allowed characters: lowercase letters, digits, dot, hyphen, underscore; exactly one "/".
  Rules: .githooks/branch-rules.json
  Rename and push again:
    git branch -m <old-name> <prefix>/<name>
    git push -u origin <prefix>/<name>
""", file=sys.stderr)


def ruleset():
    # GitHub patterns: "*" does not match "/", so exactly two levels
    exclude = [f"refs/heads/{b}" for b in RULES["allowed"]] + ["refs/heads/*/*"]
    return {"name": "Branch names", "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": ["~ALL"], "exclude": exclude}},
            "rules": [{"type": "creation"}], "bypass_actors": []}


def main(argv):
    if "--ruleset" in argv:
        print(json.dumps(ruleset(), ensure_ascii=False, indent=2))
        return 0
    if "--name" in argv:
        name = argv[argv.index("--name") + 1]
        if ok(name):
            print(f'"{name}" is allowed.')
            return 0
        report(name)
        return 1
    fail = 0
    for line in sys.stdin:
        p = line.split()
        # only check newly created branches (like the GitHub ruleset); deleting and updating stay allowed
        if len(p) != 4 or not p[2].startswith("refs/heads/") or p[1] == ZERO or p[3] != ZERO:
            continue
        name = p[2][len("refs/heads/"):]
        if not ok(name):
            report(name)
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
