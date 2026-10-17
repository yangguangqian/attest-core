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