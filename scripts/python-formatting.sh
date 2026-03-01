#!/bin/bash

set -u

MODE="check"
[[ "${1:-}" == "--fix" ]] && MODE="fix"

EXCLUDES=(
  "./venv"
  "./law"
  "./build"
  "./.git"
  "./miniforge"
  "./CROWN/build"
  "./tarballs"
)

# Build prune expression
PRUNE_ARGS=()
for d in "${EXCLUDES[@]}"; do
  PRUNE_ARGS+=( -path "$d" -o )
done
unset 'PRUNE_ARGS[${#PRUNE_ARGS[@]}-1]'  # remove trailing -o

FOUND_ISSUE=0

while IFS= read -r -d '' file; do
  echo "Checking $file"

  if [[ "$MODE" == "fix" ]]; then
    black "$file" || FOUND_ISSUE=1
  else
    if ! black --check "$file"; then
      black --diff "$file" 2>/dev/null
      FOUND_ISSUE=1
    fi
  fi

done < <(find . \( "${PRUNE_ARGS[@]}" \) -prune -o -name "*.py" -print0)

exit $FOUND_ISSUE
