# Branch naming rules: setup guide for another repository

Use this file as instructions for GitHub Copilot (agent mode) or any other assistant: open the target repository, attach this file, and say *"Set up the branch naming rules described in branch-naming-setup.md"*.

## Goal

New branches must use **two levels: `<prefix>/<name>`**.

- `<prefix>`: a type such as `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, or the user's ID (for personal work).
- `<name>`: a functional name, e.g. `garmin-tokens`.
- Allowed characters: lowercase letters, digits, dot, hyphen, underscore; exactly one `/`.
- Flat names (`fix-garmin-tokens`) and deeper names (`feat/a/b`) are rejected **when the branch is created**. Existing branches can still be updated and deleted.
- The default branch (`main`) is always allowed.

Enforcement has two layers:

1. **Local pre-push hook** (versioned in the repo): rejects the push before anything reaches GitHub and prints a clear message.
2. **GitHub ruleset** (on the server): blocks branch creation for everyone, even without the hook.

## Requirements

- Git (on Windows: Git for Windows, which provides `sh` for hooks)
- Python 3.6+ callable as `py`, `python3` or `python` (standard library only, no packages)
- Admin rights on the GitHub repository for the ruleset

## Instructions for the assistant

Do exactly the following in the target repository. Do not change other files. Commit on a branch named `ci/branch-naming-rules` (it follows the new rule), not directly on the default branch.

1. Find the default branch name (`git symbolic-ref refs/remotes/origin/HEAD` or the GitHub settings). If it is not `main`, replace `"main"` in `allowed` in `branch-rules.json` below.
2. Create the files below with exactly this content:
   - `.githooks/branch-rules.json`
   - `.githooks/branch_check.py`
   - `.githooks/pre-push`
   - `tools/setup-git-hooks.bat`
   - `tools/setup-git-hooks.sh`
3. Append the lines from the `.gitattributes` section to `.gitattributes` (create it if missing). This keeps the hooks LF so `sh` can run them on Windows.
4. Mark the hooks executable in Git: `git add .githooks && git update-index --chmod=+x .githooks/pre-push tools/setup-git-hooks.sh`
5. Generate the ruleset file from the rules (do not write it by hand):
   `py .githooks/branch_check.py --ruleset > .github/rulesets/branch-names.json`
   (use `python3` instead of `py` on macOS/Linux). Make sure the file is UTF-8 without BOM.
6. Enable the hook in the local clone: `git config core.hooksPath .githooks`
7. Run the checks in the **Verification** section and report the results.
8. Add the **README section** below to the repository's README.
9. Do not create the GitHub ruleset yourself unless the user asks; tell the user how to import it (see **GitHub ruleset**).

### `.githooks/branch-rules.json`

```json
{
  "description": "New branches must use two levels: <prefix>/<name>: prefix = e.g. feat, fix or your userID; name = functional name. Flat names without a slash are rejected. Checked by the hook .githooks/pre-push. Generate the GitHub ruleset with: py .githooks/branch_check.py --ruleset > .github/rulesets/branch-names.json",
  "allowed": ["main"],
  "prefix_pattern": "^[a-z0-9][a-z0-9._-]*$",
  "name_pattern": "^[a-z0-9][a-z0-9._-]*$",
  "prefix_examples": {
    "feat": "new feature",
    "fix": "bug fix",
    "chore": "maintenance, dependencies",
    "docs": "documentation",
    "refactor": "restructuring without new features",
    "test": "tests",
    "ci": "workflow, build",
    "<userID>": "personal work under your user ID"
  }
}
```

Fields:

| Field | Meaning |
|---|---|
| `allowed` | Exact branch names that are always allowed (default branch, maybe `develop`) |
| `prefix_pattern` | Regex for the part before `/` |
| `name_pattern` | Regex for the part after `/` |
| `prefix_examples` | Only shown in the error message; not enforced. To restrict prefixes to a fixed list, change `prefix_pattern`, e.g. `^(feat\|fix\|chore\|docs\|refactor\|test\|ci)$` (the GitHub ruleset still allows any prefix then). |

### `.githooks/branch_check.py`

```python
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
```

### `.githooks/pre-push`

```sh
#!/bin/sh
# New branches only as prefix/name; rules in .githooks/branch-rules.json, check in branch_check.py.
# Enable once per clone: git config core.hooksPath .githooks  (or tools/setup-git-hooks.bat / .sh)
dir=$(dirname "$0")
for py in py python3 python; do
  if command -v $py >/dev/null 2>&1; then exec $py "$dir/branch_check.py"; fi
done
echo "pre-push: Python not found, branch names are not checked." >&2
exit 0
```

### `tools/setup-git-hooks.bat` (Windows)

```bat
@echo off
rem Enables the Git hooks in .githooks (new branches only as prefix/name). Run once per clone.
cd /d "%~dp0.."
git config core.hooksPath .githooks || (echo Git not found. & pause & exit /b 1)
echo Git hooks enabled: new branches only as ^<prefix^>/^<name^>, e.g. fix/login-timeout or ^<userID^>/experiment.
echo Rules: .githooks\branch-rules.json
pause
```

### `tools/setup-git-hooks.sh` (macOS/Linux/Git Bash)

```sh
#!/bin/sh
# Enables the Git hooks in .githooks (new branches only as prefix/name). Run once per clone.
cd "$(dirname "$0")/.." || exit 1
git config core.hooksPath .githooks || exit 1
echo "Git hooks enabled: new branches only as <prefix>/<name>, e.g. fix/login-timeout or <userID>/experiment."
echo "Rules: .githooks/branch-rules.json"
```

### `.gitattributes` (append)

```gitattributes
# Git hooks run under sh/Python: always LF
.githooks/* text eol=lf
tools/*.sh text eol=lf
```

### Expected `.github/rulesets/branch-names.json` (generated in step 5)

```json
{
  "name": "Branch names",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~ALL"],
      "exclude": ["refs/heads/main", "refs/heads/*/*"]
    }
  },
  "rules": [{ "type": "creation" }],
  "bypass_actors": []
}
```

## Verification

Run in the repository root (Git Bash on Windows). All results must match.

```sh
S=1111111111111111111111111111111111111111; Z=0000000000000000000000000000000000000000
for b in main fix/login-timeout feat/new-report jdoe/experiment fix-login-timeout new-report feat/a/b Fix/Upper; do
  printf "refs/heads/x $S refs/heads/$b $Z\n" | sh .githooks/pre-push 2>/dev/null; echo "$b -> $?"
done
```

| Branch | Expected exit code |
|---|---|
| `main`, `fix/login-timeout`, `feat/new-report`, `jdoe/experiment` | 0 (allowed) |
| `fix-login-timeout`, `new-report`, `feat/a/b`, `Fix/Upper` | 1 (rejected) |

Also check:

- Updating an existing branch is allowed: `printf "refs/heads/x $S refs/heads/old-flat $S\n" | sh .githooks/pre-push; echo $?` → `0`
- Real push, without sending anything: `git push --dry-run origin HEAD:refs/heads/flat-test-name` → prints `Push rejected: branch name "flat-test-name" is not allowed.` and fails.
- `git config core.hooksPath` → `.githooks`

## GitHub ruleset

The hook only works where it is enabled and can be skipped with `git push --no-verify`. The ruleset enforces the rule on GitHub for everyone.

**Import in the browser:** repository → **Settings → Rules → Rulesets → New ruleset → Import a ruleset** → select `.github/rulesets/branch-names.json` → **Create**.

**Or with the GitHub CLI** (admin rights needed):

```sh
gh api -X POST repos/OWNER/REPO/rulesets --input .github/rulesets/branch-names.json
```

After changing `allowed` in `branch-rules.json`, regenerate the file (step 5) and update the ruleset on GitHub (edit it, or delete and import again).

Differences between hook and ruleset:

- The ruleset cannot check upper case or the character set; the hook can.
- On GitHub, the push fails with a generic "cannot create ref" message; only the hook prints the explanation.
- `bypass_actors` is empty, so the rule applies to admins too. Add bypass actors in the GitHub settings if needed.

## README section (add to the target repository)

```markdown
## Branch names

New branches must use two levels: `<prefix>/<name>`, e.g. `fix/login-timeout`, `feat/new-report` or `<userID>/experiment`. Flat names like `fix-login-timeout` are rejected when the branch is created.

- Rules: `.githooks/branch-rules.json`
- Enable the local check once per clone: `tools\setup-git-hooks.bat` (Windows) or `sh tools/setup-git-hooks.sh`
- Check a name: `py .githooks/branch_check.py --name fix/login-timeout`
- On GitHub the rule is enforced by the ruleset `.github/rulesets/branch-names.json`.
```

## Existing flat branches

The rule does not touch existing branches. List them with:

```sh
git ls-remote --heads origin | sed 's#.*refs/heads/##' | grep -v '/' | grep -vx main
```

Rename them only after asking the owner (renaming a remote branch = push the new name, delete the old one, open PRs must be retargeted).
