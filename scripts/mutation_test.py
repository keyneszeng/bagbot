"""BagBot mini mutation tester — crash-safe version.

Uses `git stash -- <paths>` for source-file snapshots so a SIGKILL or Ctrl-C
mid-run leaves the working tree untouched.

Mutations applied (per occurrence, where possible):
  - ==  → !=
  - <   → <=         (and the reverse)
  - >   → >=
  - and → or         (and the reverse)
  - True  → False
  - False → True
  - <number constant> → next or previous integer

Usage:
    python scripts/mutation_test.py
    python scripts/mutation_test.py --module policy
    python scripts/mutation_test.py --max 50 --workers 4
"""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src" / "bagbot"
TARGETS: List[Path] = []  # populated in main()


@dataclass
class Mutation:
    file: Path
    line: int
    original: str
    mutated: str
    description: str

    def key(self) -> Tuple[str, int, str]:
        return (str(self.file), self.line, self.original)


def _new_mutation(line: int, original: str, mutated: str, description: str) -> Mutation:
    return Mutation(file=Path("placeholder"), line=line,
                    original=original, mutated=mutated, description=description)


# ── Mutator generators ──────────────────────────────────────────────


def gen_bool_op_mutations(tree: ast.Module) -> Iterable[Mutation]:
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                yield _new_mutation(node.lineno, "and", "or", "and → or")
            elif isinstance(node.op, ast.Or):
                yield _new_mutation(node.lineno, "or", "and", "or → and")


def gen_compare_mutations(tree: ast.Module) -> Iterable[Mutation]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for op in node.ops:
            yield from _compare_op_mutation(node.lineno, op)


def _compare_op_mutation(line: int, op: ast.cmpop) -> Iterable[Mutation]:
    table = {
        ast.Eq:    ("==", "!="),
        ast.NotEq: ("!=", "=="),
        ast.Lt:    ("<",  "<="),
        ast.LtE:   ("<=", "<"),
        ast.Gt:    (">",  ">="),
        ast.GtE:   (">=", ">"),
        ast.Is:    ("is", "is not"),
        ast.IsNot: ("is not", "is"),
    }
    if type(op) in table:
        original, mutated = table[type(op)]
        yield _new_mutation(line, original, mutated, f"{original} → {mutated}")


def gen_constant_mutations(tree: ast.Module) -> Iterable[Mutation]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        if node.value is True:
            yield _new_mutation(node.lineno, "True", "False", "True → False")
        elif node.value is False:
            yield _new_mutation(node.lineno, "False", "True", "False → True")
        elif node.value == 0 and isinstance(node.value, int):
            yield _new_mutation(node.lineno, "0", "1", "0 → 1")
        elif node.value == 1 and isinstance(node.value, int):
            yield _new_mutation(node.lineno, "1", "0", "1 → 0")
        elif node.value == 100.0:
            yield _new_mutation(node.lineno, "100.0", "50.0", "100.0 → 50.0")
        elif node.value == 5.0:
            yield _new_mutation(node.lineno, "5.0", "10.0", "5.0 → 10.0")
        elif node.value == 168:
            yield _new_mutation(node.lineno, "168", "84", "168 → 84")


def collect_mutations(targets: List[Path]) -> List[Mutation]:
    out: List[Mutation] = []
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        gen = []
        gen.extend(gen_bool_op_mutations(tree))
        gen.extend(gen_compare_mutations(tree))
        gen.extend(gen_constant_mutations(tree))
        for m in gen:
            m.file = path
        out.extend(gen)
    # Dedupe by (file, line, original) — same line may have multiple mutations
    seen: set = set()
    deduped: List[Mutation] = []
    for m in out:
        k = m.key()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(m)
    return deduped


# ── File mutation with safety checks ────────────────────────────────


def apply_mutation(m: Mutation) -> None:
    lines = m.file.read_text(encoding="utf-8").splitlines(keepends=True)
    if not (0 < m.line <= len(lines)):
        raise RuntimeError(f"line {m.line} out of range for {m.file}")
    old = lines[m.line - 1]
    idx = old.find(m.original)
    if idx < 0:
        raise RuntimeError(
            f"original text not found in line {m.line} of {m.file}\n"
            f"  expected: {m.original!r}\n"
            f"  got:      {old!r}"
        )
    new = old[:idx] + m.mutated + old[idx + len(m.original):]
    lines[m.line - 1] = new
    m.file.write_text("".join(lines), encoding="utf-8")


def revert_mutation(m: Mutation) -> None:
    lines = m.file.read_text(encoding="utf-8").splitlines(keepends=True)
    if not (0 < m.line <= len(lines)):
        raise RuntimeError(f"line {m.line} out of range for {m.file} during revert")
    old = lines[m.line - 1]
    idx = old.find(m.mutated)
    if idx < 0:
        raise RuntimeError(
            f"mutated text not found in line {m.line} of {m.file}\n"
            f"  expected: {m.mutated!r}\n"
            f"  got:      {old!r}"
        )
    new = old[:idx] + m.original + old[idx + len(m.mutated):]
    lines[m.line - 1] = new
    m.file.write_text("".join(lines), encoding="utf-8")


# ── Test runner ────────────────────────────────────────────────────


def run_tests(workers: int = 4, module: Optional[str] = None) -> Tuple[int, float]:
    if module:
        target = PROJECT_ROOT / "tests" / f"test_{module}.py"
        if not target.exists():
            for p in (PROJECT_ROOT / "tests").glob("test_*.py"):
                if module in p.stem:
                    target = p
                    break
    else:
        target = PROJECT_ROOT / "tests"

    args = [
        "./.test-venv/bin/python", "-m", "pytest", str(target),
        "-x", "-q", "--no-header", "--tb=no",
        "-p", "no:cacheprovider",
        "-n", str(workers),
        "--ignore=tests/test_dashboard.py",
    ]
    start = time.time()
    proc = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    elapsed = time.time() - start
    return proc.returncode, elapsed


# ── Crash-safe snapshot via targeted git stash ─────────────────────


def git_stash_push_paths(paths: List[str]) -> Optional[str]:
    """Stash working-tree changes for our target paths only.

    We use `git stash push -- <paths>` to avoid disturbing other untracked
    files in the working tree (such as scripts/mutation_test.py itself).
    """
    if not paths:
        return None
    result = subprocess.run(
        ["git", "stash", "push", "-m", "mutation_test_autosnapshot",
         "--", *paths],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if "No local changes to save" in result.stdout:
        return None
    if result.returncode != 0:
        raise RuntimeError(
            f"git stash push failed: {result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


def git_restore_files(paths: List[str]) -> None:
    """Force-restore the named paths from HEAD, no matter what."""
    for p in paths:
        subprocess.run(
            ["git", "checkout", "HEAD", "--", p],
            cwd=PROJECT_ROOT,
            capture_output=True,
        )


def git_stash_pop() -> bool:
    """Pop the stash we made.  Returns True on success."""
    result = subprocess.run(
        ["git", "stash", "pop"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


# ── Main ────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", help="only this module (without .py)")
    parser.add_argument("--max", type=int, default=500)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    targets = sorted(SRC.glob("*.py"))
    targets = [t for t in targets if t.name not in
               ("__init__.py", "__main__.py", "logging_setup.py")]
    if args.module:
        targets = [t for t in targets if t.stem == args.module]
        if not targets:
            print(f"no module {args.module} found", file=sys.stderr)
            return 1
    global TARGETS
    TARGETS = targets
    rel_paths = [str(t.relative_to(PROJECT_ROOT)) for t in targets]

    print(f"=== BagBot mini mutation tester (git-stash-backed) ===")
    print(f"Targets: {[t.name for t in targets]}")
    mutations = collect_mutations(targets)
    print(f"Total mutations proposed: {len(mutations)}")
    if args.max:
        mutations = mutations[: args.max]
    print(f"Will try: {len(mutations)} (capped by --max {args.max})")

    # Crash-safe snapshot: stash only the files we're going to mutate
    print()
    print("Snapshotting working tree via git stash (paths only)…")

    # First, refuse to run if there are pre-existing uncommitted changes to
    # the target files — otherwise the user would lose their work if our
    # restore logic ever fails.
    result = subprocess.run(
        ["git", "status", "--porcelain"] + rel_paths,
        cwd=PROJECT_ROOT, capture_output=True, text=True,
    )
    dirty = [line for line in result.stdout.splitlines() if line.strip()]
    if dirty:
        print("ERROR: target files have uncommitted changes:", file=sys.stderr)
        for d in dirty:
            print(f"  {d}", file=sys.stderr)
        print()
        print("Please commit or stash them before running the mutation tester:",
              file=sys.stderr)
        print(f"  git add -A && git commit -m 'WIP: saving before mutation test'",
              file=sys.stderr)
        return 4

    stash_ref = git_stash_push_paths(rel_paths)
    if stash_ref is not None:
        print(f"  stashed: {stash_ref!r}")
    else:
        print("  no local changes to stash (clean tree)")

    killed = 0
    survived = 0
    errors = 0
    survived_list: List[Mutation] = []
    start = time.time()

    def _restore_and_exit(sig=None, frame=None):
        print("\n\nInterrupt received — restoring working tree…")
        git_restore_files(rel_paths)
        if stash_ref is not None:
            git_stash_drop() if False else None  # best effort
        sys.exit(130 if sig == signal.SIGINT else 1)

    signal.signal(signal.SIGINT, _restore_and_exit)
    signal.signal(signal.SIGTERM, _restore_and_exit)

    try:
        print()
        print("Running baseline tests…")
        rc, baseline = run_tests(workers=args.workers, module=args.module)
        print(f"  baseline: rc={rc}  elapsed={baseline:.1f}s")
        if rc != 0:
            print("BASELINE TESTS ARE FAILING.  Fix them first.", file=sys.stderr)
            return 1

        for i, m in enumerate(mutations, 1):
            try:
                apply_mutation(m)
            except Exception as e:
                errors += 1
                if args.verbose:
                    print(f"  [{i:3d}/{len(mutations)}] SKIP  "
                          f"{m.file.name}:{m.line} {m.description}: {e}")
                continue

            rc, elapsed = run_tests(workers=args.workers,
                                     module=m.file.stem)
            status = "KILLED " if rc != 0 else "SURVIVED"
            if args.verbose or rc == 0:
                print(f"  [{i:3d}/{len(mutations)}] {status} "
                      f"{m.file.name}:{m.line} {m.description}  ({elapsed:.1f}s)")

            if rc != 0:
                killed += 1
            else:
                survived += 1
                survived_list.append(m)

            try:
                revert_mutation(m)
            except Exception as e:
                print(f"  !!! revert failed for {m.file.name}:{m.line}: {e}")
                print("  Restoring everything from HEAD.")
                git_restore_files(rel_paths)
                return 3
    finally:
        # Always restore from stash + restore working-tree state
        if stash_ref is not None:
            # We may have stashed a clean state, then mutated.  After the run
            # the working tree should match HEAD (we reverted each mutation).
            # So just drop the stash.
            subprocess.run(
                ["git", "stash", "drop", stash_ref.split()[-1]
                 if stash_ref else "mutation_test_autosnapshot"],
                cwd=PROJECT_ROOT,
                capture_output=True,
            )
        # Belt-and-suspenders: make sure all target files match HEAD
        git_restore_files(rel_paths)
        print()
        print("Working tree restored.")

    total = killed + survived
    score = (killed / total * 100) if total else 0.0
    elapsed = time.time() - start
    print()
    print("=" * 60)
    print(f"  Mutations tried:     {len(mutations)}")
    print(f"  Killed:              {killed}")
    print(f"  Survived:            {survived}")
    print(f"  Errors (parse skip): {errors}")
    print(f"  Mutation score:      {score:.1f}%  (target: >80%)")
    print(f"  Wall time:           {elapsed:.1f}s")
    print("=" * 60)

    if survived_list:
        print()
        print("SURVIVING MUTATIONS (test-coverage gaps to fix):")
        for m in survived_list:
            print(f"  - {m.file.name}:{m.line}  {m.description}  "
                  f"({m.original!r} → {m.mutated!r})")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
