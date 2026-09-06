#!/usr/bin/env bash
# Regenerate the captured terraform output that the test suite parses.
#
# Run this after changing examples/terraform, or when a new Terraform release
# changes the shape of `terraform show` output. It leaves the example project
# applied and unmodified.
#
#   make example-apply && ./scripts/capture-fixtures.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$root/examples/terraform"
fixtures="$root/tests/fixtures"
target="random_integer.random_number"

work="$(mktemp -d)"
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

cd "$project"
mkdir -p "$fixtures" generated

# Start from a fully applied project so every capture below is reproducible.
echo "==> applying the example project"
terraform apply -auto-approve -no-color >/dev/null

echo "==> state (text and json)"
terraform show -no-color > "$fixtures/state_show.txt"
terraform show -json > "$fixtures/state_show.json"

echo "==> state with a tainted resource"
terraform taint "$target" >/dev/null
terraform show -no-color > "$fixtures/state_tainted.txt"
terraform untaint "$target" >/dev/null

echo "==> plan with pending creations"
# Every generated file is owned by exactly one module instance, so removing
# them all yields a stable count that the tests can assert on.
rm -f generated/*
terraform plan -no-color -input=false -detailed-exitcode -out="$work/changes.plan" \
    > "$fixtures/plan_changes.txt" 2>&1 || true
terraform apply -auto-approve -no-color >/dev/null

echo "==> plan with a forced replacement"
cp modules/beta/main.tf "$work/beta.tf.bak"
restore() { cp "$work/beta.tf.bak" "$project/modules/beta/main.tf" 2>/dev/null || true; cleanup; }
trap restore EXIT
# file_permission is ForceNew for the local provider, so this produces a
# replacement plan complete with `~ old -> new` diff lines.
awk '{ if ($1 == "filename") print "  file_permission = \"0644\""; print }' \
    "$work/beta.tf.bak" > modules/beta/main.tf
terraform plan -no-color -input=false -out="$work/replace.plan" \
    > "$fixtures/plan_replace.txt" 2>&1 || true
cp "$work/beta.tf.bak" modules/beta/main.tf

echo
echo "Fixtures written:"
ls -l "$fixtures"
echo
echo "Review the diff before committing: the tests encode these resource counts."
