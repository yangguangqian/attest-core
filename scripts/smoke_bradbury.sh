#!/usr/bin/env bash
# One-shot smoke test for AttestCore on Bradbury.
# - retries transient write reverts (Bradbury flaps)
# - waits for ACCEPTED, not FINALIZED (Bradbury appeal window ~30 min)
set -euo pipefail

ADDRESS="${ADDRESS:-0xa66d2F952E063e6BD69f7B5157CE0119f5F86796}"
CLAIM_ID="${CLAIM_ID:-smoke-$(date +%Y%m%d%H%M%S)}"
TOLERANCE_BP="${TOLERANCE_BP:-100}"
MIN_SOURCES="${MIN_SOURCES:-1}"
EVIDENCE_DIR="${EVIDENCE_DIR:-evidence}"
MAX_WRITE_TRIES="${MAX_WRITE_TRIES:-6}"

SOURCES='["https://registry.npmjs.org/leftpad","https://cdn.jsdelivr.net/npm/leftpad/package.json"]'
REG_LOG="$EVIDENCE_DIR/bradbury-register_claim.log"
RES_LOG="$EVIDENCE_DIR/bradbury-resolve.log"

command -v genlayer >/dev/null 2>&1 || { echo "genlayer not on PATH"; exit 1; }
mkdir -p "$EVIDENCE_DIR"

step() { printf '\n[%s] == %s ==\n' "$(date +%H:%M:%S)" "$*"; }
last_tx() { grep -oE '0x[0-9a-fA-F]{64}' "$1" | tail -n1; }

# write with retry on transient reverts; appends output to $1, echoes ONLY the tx hash
retry_write() {
  local f="$1"; shift
  local n=0
  while :; do
    n=$((n+1))
    printf '\n--- write attempt %d: %s\n' "$n" "$*" >>"$f"
    if genlayer write "$@" >>"$f" 2>&1; then
      last_tx "$f"; return 0
    fi
    echo "  attempt $n reverted (transient?), retrying in 5s" >&2
    if [ "$n" -ge "$MAX_WRITE_TRIES" ]; then
      echo "  !! giving up after $n attempts — see $f" >&2; return 1
    fi
    sleep 5
  done
}

step "unlock + network"
genlayer account unlock || true
genlayer network set testnet-bradbury >/dev/null
genlayer network info | tee -a "$REG_LOG"
genlayer account      | tee -a "$REG_LOG"

step "register_claim"
REG_TX="$(retry_write "$REG_LOG" "$ADDRESS" register_claim --args "$CLAIM_ID" "latest version?" "$SOURCES" num "$TOLERANCE_BP" "$MIN_SOURCES")"
step "register tx = $REG_TX"
genlayer receipt "$REG_TX" --status ACCEPTED --retries 90 --interval 4000 | tee -a "$REG_LOG" || true

step "resolve"
RES_TX="$(retry_write "$RES_LOG" "$ADDRESS" resolve --args "$CLAIM_ID")"
step "resolve tx = $RES_TX"
genlayer receipt "$RES_TX" --status ACCEPTED --retries 90 --interval 4000 | tee -a "$RES_LOG" || true

step "read"
genlayer call "$ADDRESS" get_fact --args "$CLAIM_ID" | tee -a "$RES_LOG"
genlayer call "$ADDRESS" get_band --args "$CLAIM_ID" | tee -a "$RES_LOG"

step "done — CHECK band=QUORUM and value is a canonical bucket"