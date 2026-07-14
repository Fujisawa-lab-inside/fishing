#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PNPM=${PNPM:-/Users/swarm/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm}
NODE_BIN=${NODE_BIN:-/Users/swarm/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin}
PATH="$NODE_BIN:$PATH"
OUT="$ROOT/public/wasm"
mkdir -p "$OUT"
"$PNPM" --package=wabt@1.0.37 dlx wat2wasm \
  "$ROOT/wasm/stage20-reference-kernel.wat" \
  -o "$OUT/stage20-reference-kernel-v1.wasm"
"$PNPM" --package=wabt@1.0.37 dlx wasm-validate \
  "$OUT/stage20-reference-kernel-v1.wasm"
shasum -a 256 "$OUT/stage20-reference-kernel-v1.wasm"
