#!/bin/bash
# Put sonar/macro and sonar/playmaker here as real git checkouts at the commits
# CI pins in .github/workflows/tests.yml.
#
#   scripts/bootstrap_nested.sh           clone what is absent, replace copies
#   scripts/bootstrap_nested.sh --move    also move a clean repo that is off its pin
#
# Why: the nested repos are git-ignored here (repo-per-module), so a worktree
# never contains them, and a release built from one held plain copies that no
# commit names. v2.340 went out like that (docs/specs/build-traceability.md).
# check_app.sh now refuses such a bundle; this is the step that makes the tree
# buildable (RUNBOOK section 1).
#
# Per repo (A5):
#   absent             clone at the pin
#   a copy (no .git)   clone first, report how the copy differs from the pin,
#                      move the copy aside to .nested-bootstrap/ (never deleted)
#   uncommitted work   refused, untouched
#   clean, at the pin  nothing to do
#   clean, off the pin refused (it may be the owner's working repo); --move
#                      checks the pin out and prints how to go back
# The clone comes from the wwds-dev remote, on the outer origin's transport; if
# that fails, from the main checkout's local repo, with a warning (owner Q2).
# Each run's per-repo summary is also written to .nested-bootstrap/report-*.txt
# so Verify can paste it into docs/audit/build-traceability-verify.md.
set -euo pipefail
cd "$(dirname "$0")/.."
TOP="$(git rev-parse --show-toplevel)"
cd "$TOP"

MOVE=0
case "${1:-}" in
  --move) MOVE=1 ;;
  "") ;;
  *) echo "usage: $0 [--move]"; exit 2 ;;
esac

WORK="$TOP/.nested-bootstrap"
mkdir -p "$WORK"
# Sessions share worktrees: one bootstrap at a time. mkdir is atomic.
if ! mkdir "$WORK/lock" 2>/dev/null; then
  echo "error: another bootstrap holds $WORK/lock; nothing was touched."
  echo "(If none is running, remove that directory.)"
  exit 1
fi
TMPS=()
cleanup() {
  local t
  for t in "${TMPS[@]+"${TMPS[@]}"}"; do rm -rf "$t"; done
  rmdir "$WORK/lock" 2>/dev/null || true
}
trap cleanup EXIT

# A parse error stops here, before anything is touched.
if ! PINS="$(python3 -I scripts/buildid.py pins --shell .github/workflows/tests.yml)"; then
  echo "error: cannot read the CI pins from .github/workflows/tests.yml; nothing was touched."
  exit 1
fi
ORIGIN="$(git remote get-url origin 2>/dev/null || true)"

# The main checkout, for the local fallback: the first worktree record, checked
# against the common git dir. Disagreeing, or this tree itself: no fallback.
real() { (cd "$1" 2>/dev/null && pwd -P) || true; }
MAIN="$(real "$(git worktree list --porcelain | sed -n '1s/^worktree //p')")"
COMMON="$(real "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")"
[[ -n "$MAIN" && "$MAIN" == "$COMMON" ]] || MAIN=""
[[ "$MAIN" == "$(real "$TOP")" ]] && MAIN=""

REPORT="$WORK/report-$(date -u +%Y%m%dT%H%M%SZ).txt"
say() { echo "$*"; echo "$*" >> "$REPORT"; }
say "bootstrap_nested $(date -u +%Y-%m-%dT%H:%M:%SZ) in $TOP"

# git that never prompts and never hangs on a dead network (security P3-3),
# and re-hashes what it receives (P3-4).
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10"
NET=(-c credential.interactive=never -c http.lowSpeedLimit=1 -c http.lowSpeedTime=30
     -c transfer.fsckObjects=true)
# A URL as printed: without userinfo (code review P3-4, security P3-2).
shown() { sed -E 's#^([A-Za-z][A-Za-z0-9+.-]*://)[^/@]*@#\1#' <<<"$1"; }

# Clones <name> at <sha> into a temporary dir; sets CLONED and SOURCE. Called
# from `if`, where set -e is off: every step is checked by hand (code review P3-2).
clone_pin() {
  local name=$1 repository=$2 sha=$3 url tmp ref refs
  if ! url="$(python3 -I scripts/buildid.py remote-url "$ORIGIN" "$repository" 2>&1)"; then
    say "error: $name: ${url#error: }; nothing moved."
    return 1
  fi
  tmp="$WORK/$name.tmp.$$"
  rm -rf "$tmp"
  TMPS+=("$tmp")
  if git "${NET[@]}" clone --quiet --no-checkout -- "$url" "$tmp" 2>/dev/null; then
    SOURCE="$(shown "$url")"
  else
    rm -rf "$tmp"
    if [[ -z "$MAIN" || ! -e "$MAIN/sonar/$name/.git" ]] \
        || ! git "${NET[@]}" clone --quiet --no-local --no-checkout -- "$MAIN/sonar/$name" "$tmp" \
             2>/dev/null; then
      say "error: $name: cannot clone $(shown "$url"), and there is no local fallback; nothing moved."
      return 1
    fi
    if ! git -C "$tmp" remote set-url origin "$url"; then
      say "error: $name: could not set the clone's origin; nothing moved."
      return 1
    fi
    # Its origin/* refs are the main checkout's local branches, not the
    # remote's: drop them, so the gate's "on origin" check cannot be fooled.
    if ! refs="$(git -C "$tmp" for-each-ref --format='%(refname)' refs/remotes/origin)"; then
      say "error: $name: could not list the clone's origin refs; nothing moved."
      return 1
    fi
    for ref in $refs; do
      if ! git -C "$tmp" update-ref --no-deref -d "$ref"; then
        say "error: $name: could not drop $ref from the clone; nothing moved."
        return 1
      fi
    done
    if [[ -n "$(git -C "$tmp" for-each-ref refs/remotes/origin 2>&1)" ]]; then
      say "error: $name: the clone still has origin refs from the main checkout; nothing moved."
      return 1
    fi
    SOURCE="$MAIN/sonar/$name"
    say "WARNING: $name cloned from the main checkout's local repo ($SOURCE), not $(shown "$url"):" \
        "the remote was unreachable; pin ${sha:0:9} may not be pushed." \
        "Run git -C sonar/$name fetch once it is reachable."
  fi
  if ! git -C "$tmp" cat-file -e "$sha^{commit}" 2>/dev/null; then
    say "error: $name: pin ${sha:0:9} is not in $SOURCE; nothing moved."
    return 1
  fi
  if ! git -C "$tmp" -c advice.detachedHead=false checkout --quiet --detach "$sha"; then
    say "error: $name: pin ${sha:0:9} could not be checked out; nothing moved."
    return 1
  fi
  CLONED="$tmp"
}

FAILED=0
while read -r path repository sha <&3; do
  name="${path#sonar/}"
  if [[ -L "$path" ]]; then
    # --move and the copy steps would act on whatever it points at (security P3-6).
    say "error: $path is a symlink; replace it with a directory or remove it yourself."
    FAILED=1; continue
  fi
  if [[ ! -e "$path" ]]; then
    if clone_pin "$name" "$repository" "$sha"; then
      if [[ -e "$path" ]]; then
        say "error: $path appeared while cloning; left alone."; FAILED=1; continue
      fi
      mkdir -p "$(dirname "$path")"
      mv "$CLONED" "$path"
      say "$name: cloned at the pin ${sha:0:9} from $SOURCE"
    else
      FAILED=1
    fi
  elif [[ ! -e "$path/.git" ]]; then
    clone_pin "$name" "$repository" "$sha" || { FAILED=1; continue; }
    diffs="$(diff -rq -x __pycache__ -x '*.pyc' -x .DS_Store -x .git "$path" "$CLONED" || true)"
    if [[ -z "$diffs" ]]; then
      say "$name: the copy was identical to the pin ${sha:0:9}"
    else
      n="$(grep -c . <<<"$diffs")"
      say "$name: the copy differed from the pin ${sha:0:9} in $n files:"
      while IFS= read -r line; do say "  $line"; done <<<"$(head -15 <<<"$diffs")"
      [[ "$n" -gt 15 ]] && say "  (and $((n - 15)) more)"
    fi
    aside="$WORK/$name.copy-$(date -u +%Y%m%dT%H%M%S)"
    if ! mv "$path" "$aside"; then
      say "error: $name: could not move the copy aside; left in place."
      FAILED=1; continue
    fi
    say "$name: copy moved to $aside"
    if ! mv "$CLONED" "$path"; then
      if mv "$aside" "$path"; then
        say "error: $name: the clone could not be put in place; the copy was moved back."
      else
        say "error: $name: the clone could not be put in place, and the copy stays at $aside."
      fi
      FAILED=1; continue
    fi
    say "$name: cloned at the pin from $SOURCE"
  else
    if ! st="$(git -C "$path" status --porcelain --untracked-files=no 2>/dev/null)" \
        || [[ -n "$st" ]]; then
      say "error: $name has uncommitted work (or git cannot read it); commit or set it aside yourself."
      FAILED=1; continue
    fi
    head="$(git -C "$path" rev-parse HEAD 2>/dev/null || true)"
    branch="$(git -C "$path" symbolic-ref -q --short HEAD 2>/dev/null || echo "(detached)")"
    if [[ "$head" == "$sha" ]]; then
      say "$name: already at the pin ${sha:0:9}"
    elif [[ "$MOVE" != 1 ]]; then
      say "error: $name is at ${head:0:9} on $branch, but CI pins ${sha:0:9}. Either move it:"
      say "  git -C $path fetch origin && git -C $path checkout --detach $sha"
      say "  (or: $0 --move)"
      say "or commit, push and bump the pin in .github/workflows/tests.yml."
      FAILED=1
    else
      if ! git -C "$path" cat-file -e "$sha^{commit}" 2>/dev/null; then
        git "${NET[@]}" -C "$path" fetch --quiet origin "$sha" 2>/dev/null || true
      fi
      if git -C "$path" -c advice.detachedHead=false checkout --quiet --detach "$sha" 2>/dev/null; then
        say "$name: moved from ${head:0:9} ($branch) to the pin ${sha:0:9}. To go back:"
        if [[ "$branch" == "(detached)" ]]; then
          say "  git -C $path checkout --detach $head"
        else
          say "  git -C $path checkout $branch"
        fi
      else
        say "error: $name: pin ${sha:0:9} could not be checked out (not fetched?); left at ${head:0:9}."
        FAILED=1
      fi
    fi
  fi
done 3<<<"$PINS"

# Postcondition: each is a repo, clean, at its pin.
while read -r path repository sha <&3; do
  head="$(git -C "$path" rev-parse HEAD 2>/dev/null || true)"
  if [[ ! -e "$path/.git" || "$head" != "$sha" ]] \
      || [[ -n "$(git -C "$path" status --porcelain --untracked-files=no 2>/dev/null || echo x)" ]]; then
    say "not done: $path is not a clean checkout at ${sha:0:9}."
    FAILED=1
  fi
done 3<<<"$PINS"

echo
echo "Report saved: $REPORT"
if [[ "$FAILED" != 0 ]]; then
  echo "Bootstrap incomplete (see above)."
  exit 1
fi
echo "Both nested repos are at their CI pins. Check: ./run-tests.sh tests/test_ci_pins.py -q"
