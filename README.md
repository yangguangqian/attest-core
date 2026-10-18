# AttestCore

A reusable Intelligent Contract primitive for **cross-source fact corroboration with
disagreement as first-class state**.

Most on-chain oracles resolve a fact from a single source and either succeed or fail.
AttestCore instead takes N independent source URLs for the same claim, extracts a
structured value from each with a verbatim-quote grounding check, and publishes a
**confidence band**:

| Band | Meaning |
|---|---|
| `QUORUM` | Enough grounded sources agree within tolerance |
| `CONTESTED` | Enough grounded sources, but they disagree |
| `UNRESOLVED` | Too few grounded sources — fail closed |

Disagreement is stored, not swallowed. Consumers read `is_current()` before trusting a fact.

## Why it is reusable

AttestCore is a standalone primitive, not a single app. Any contract can register a claim
and read its attested fact by ID:

```python
registry = gl.get_contract_at(ATTEST_CORE_ADDRESS)
band = registry.view().get_band("npm-leftpad-latest")
if band == "QUORUM":
    value = registry.view().get_fact("npm-leftpad-latest").value
	
## Deployed

| Network | Contract | Deploy tx | Status |
|---|---|---|---|
| Studionet | 0xd411183030e038C1D0838ECA0673e052AE7973aA | — | verified |
| Bradbury | 0x0E6c62c2F27Ab6eef1583702b5BfE1101870a104 | 0x165e63dfb053fe3488b439eb016d88321eebaec0e3b04e29102ba9b6b522831e | FINALIZED |

### End-to-end evidence (Bradbury, epoch 180)

- `register_claim` tx: 0xc2e48acb9a61952a5d19245e3c03c13f4a8ed50959b278e9c1ff9cce64d9135c — FINALIZED
- `resolve` tx: 0x5ffa181ca268be29927530c5d43424313d902bde42f988fa8d648d8791c22246 — FINALIZED
- On-chain return value of `resolve`:
  `band=QUORUM | disagree_idx=<empty> | failed_idx=<empty> | value=0.0.1`
- `get_fact("npm-leftpad")` →
  `{ band: QUORUM, value: "0.0.1", valid_sources: 2, total_sources: 2, epoch: 1, is_current: true }`
- Verbatim quotes anchored from two independent origins:
  - `"dist-tags":{"latest":"0.0.1"}` — registry.npmjs.org
  - `"version": "0.0.1"` — cdn.jsdelivr.net
- Validator convergence (5/5): `validatorVotesName = [AGREE × 5]`,
  identical `validatorResultHash` across all five validators
  (`0x1ddc7659...cd9308`)

### Raw logs

- `evidence/bradbury-register_claim.log`
- `evidence/bradbury-resolve.log`
- `evidence/result.txt` (offline direct-mode run, 10 passed)