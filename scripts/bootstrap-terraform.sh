#!/usr/bin/env bash
# Install a pinned Terraform for local development or a sandbox without one.
#
# Usage: scripts/bootstrap-terraform.sh [version] [install-dir]
set -euo pipefail

version="${1:-1.9.8}"
dest="${2:-/usr/local/bin}"

case "$(uname -s)" in
    Linux)  os=linux ;;
    Darwin) os=darwin ;;
    *) echo "unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac

case "$(uname -m)" in
    x86_64|amd64) arch=amd64 ;;
    arm64|aarch64) arch=arm64 ;;
    *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

url="https://releases.hashicorp.com/terraform/${version}/terraform_${version}_${os}_${arch}.zip"
echo "==> downloading $url"
curl -fsSL -o "$tmp/terraform.zip" "$url"

echo "==> verifying checksum"
sums="https://releases.hashicorp.com/terraform/${version}/terraform_${version}_SHA256SUMS"
curl -fsSL -o "$tmp/sums" "$sums"
expected="$(grep "terraform_${version}_${os}_${arch}.zip" "$tmp/sums" | cut -d' ' -f1)"
if command -v sha256sum >/dev/null; then
    actual="$(sha256sum "$tmp/terraform.zip" | cut -d' ' -f1)"
else
    actual="$(shasum -a 256 "$tmp/terraform.zip" | cut -d' ' -f1)"
fi
if [ "$expected" != "$actual" ]; then
    echo "checksum mismatch: expected $expected, got $actual" >&2
    exit 1
fi

unzip -o -q "$tmp/terraform.zip" -d "$tmp"
install -m 0755 "$tmp/terraform" "$dest/terraform"
"$dest/terraform" version
