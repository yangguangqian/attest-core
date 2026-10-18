# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from dataclasses import dataclass

from genlayer import *


MAX_SOURCES = 5
MAX_PAGE_CHARS = 8000
MIN_QUOTE_CHARS = 8


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def _to_float(s: str):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


def _nums_close(a: float, b: float, tolerance_bp: int) -> bool:
    base = abs(b) if b != 0 else 1.0
    return abs(a - b) / base <= tolerance_bp / 10000.0


def _build_prompt(question: str, expected_type: str, text: str) -> str:
    return (
        "Extract one fact from a web page.\n\n"
        "QUESTION: " + question + "\n"
        "EXPECTED VALUE TYPE: " + expected_type + "\n\n"
        "Return a JSON object with exactly these keys:\n"
        '  "found": true or false\n'
        '  "value": the answer as a plain string, or "" if not found\n'
        '  "quote": a SHORT verbatim substring copied from the page text\n\n'
        "Rules:\n"
        "  - the quote must appear literally in the page text, no paraphrasing\n"
        "  - keep the quote under 200 characters\n"
        "  - write numbers as digits and booleans as true or false\n\n"
        "PAGE TEXT:\n" + text
    )


def _evaluate(question, sources, expected_type, tolerance_bp, min_valid_sources):
    per = []
    for i in range(len(sources)):
        url = sources[i]
        rec = {"i": i, "ok": False, "value": "", "quote": "", "why": ""}
        try:
            resp = gl.nondet.web.get(url)
            text = resp.body.decode("utf-8")[:MAX_PAGE_CHARS]
        except Exception:
            rec["why"] = "fetch"
            per.append(rec)
            continue
        try:
            out = gl.nondet.exec_prompt(
                _build_prompt(question, expected_type, text),
                response_format="json",
            )
            rec["value"] = str(out.get("value", "")).strip()
            rec["quote"] = str(out.get("quote", "")).strip()
            if not bool(out.get("found", True)):
                rec["why"] = "notfound"
            elif len(_norm(rec["quote"])) < MIN_QUOTE_CHARS:
                rec["why"] = "quote-short"
            elif _norm(rec["quote"]) not in _norm(text):
                rec["why"] = "quote-not-grounded"
            else:
                rec["ok"] = True
        except Exception:
            rec["why"] = "llm"
        per.append(rec)

    valid = [r for r in per if r["ok"]]
    failed = [r["i"] for r in per if not r["ok"]]
    need = int(min_valid_sources)

    band = "UNRESOLVED"
    value = ""
    disagree = []

    if len(valid) >= need:
        if expected_type == "num":
            nums = []
            for r in valid:
                f = _to_float(r["value"])
                if f is not None:
                    nums.append((f, r))
            if len(nums) >= need:
                nums.sort(key=lambda t: t[0])
                lo = nums[0][0]
                hi = nums[-1][0]
                base = abs(hi) if hi != 0 else 1.0
                within = (hi - lo) / base <= int(tolerance_bp) / 10000.0
                value = nums[0][1]["value"]
                if within:
                    band = "QUORUM" if not failed else "CONTESTED"
                else:
                    band = "CONTESTED"
                    disagree = sorted([r["i"] for _, r in nums])
            else:
                band = "UNRESOLVED"
        else:
            groups = {}
            for r in valid:
                groups.setdefault(_norm(r["value"]), []).append(r)
            if len(groups) == 1:
                band = "QUORUM" if not failed else "CONTESTED"
                value = valid[0]["value"]
            else:
                band = "CONTESTED"
                biggest = max(groups.values(), key=len)
                value = biggest[0]["value"]
                disagree = sorted([r["i"] for r in valid])

    return {
        "value": value,
        "band": band,
        "valid": len(valid),
        "total": len(per),
        "failed_idx": ",".join(str(x) for x in failed),
        "disagree_idx": ",".join(str(x) for x in disagree),
        "quotes": json.dumps([r["quote"] for r in valid], sort_keys=True),
    }


@allow_storage
@dataclass
class Claim:
    question: str
    sources_json: str
    expected_type: str
    tolerance_bp: u256
    min_valid_sources: u256
    epoch: u256
    status: str
    registrant: Address
    challenger: Address
    bond: u256


@allow_storage
@dataclass
class Fact:
    value: str
    band: str
    valid_sources: u256
    total_sources: u256
    failed_idx: str
    disagree_idx: str
    quotes_json: str
    epoch: u256


class AttestCore(gl.Contract):
    claims: TreeMap[str, Claim]
    facts: TreeMap[str, Fact]
    resolutions: u256

    def __init__(self):
        self.resolutions = u256(0)

    @gl.public.write
    def register_claim(
        self,
        claim_id: str,
        question: str,
        sources_json: DynArray[str],
        expected_type: str,
        tolerance_bp: u256,
        min_valid_sources: u256,
    ):
        if claim_id in self.claims:
            raise gl.vm.UserError("claim_id already exists")
        if isinstance(sources_json, str):
            try:
                sources = json.loads(sources_json)
            except Exception:
                raise gl.vm.UserError("sources_json is not valid JSON")
        else:
            sources = [str(s) for s in sources_json]
        if len(sources) == 0 or len(sources) > MAX_SOURCES:
            raise gl.vm.UserError("sources must contain 1..5 urls")
        if expected_type not in ("str", "num", "bool"):
            raise gl.vm.UserError("expected_type must be str, num or bool")
        if int(min_valid_sources) < 1 or int(min_valid_sources) > len(sources):
            raise gl.vm.UserError("min_valid_sources out of range")
        if not question.strip():
            raise gl.vm.UserError("question is empty")

        sender = gl.message.sender_address
        self.claims[claim_id] = Claim(
            question.strip(),
            json.dumps(sources),
            expected_type,
            tolerance_bp,
            min_valid_sources,
            u256(0),
            "OPEN",
            sender,
            sender,
            u256(0),
        )

    @gl.public.write
    def resolve(self, claim_id: str):
        if claim_id not in self.claims:
            raise gl.vm.UserError("claim not found")

        c = self.claims[claim_id]
        if c.status == "STALE":
            raise gl.vm.UserError("claim is stale")

        question = c.question
        expected_type = c.expected_type
        tol = int(c.tolerance_bp)
        need = int(c.min_valid_sources)
        sources = json.loads(c.sources_json)
        if len(sources) == 0:
            raise gl.vm.UserError("claim has no sources")

        def leader_fn():
            return _evaluate(question, sources, expected_type, tol, need)

        def validator_fn(res) -> bool:
            if not isinstance(res, gl.vm.Return):
                return False
            theirs = res.calldata
            mine = _evaluate(question, sources, expected_type, tol, need)
            if mine["band"] != theirs["band"]:
                return False
            if mine["valid"] != theirs["valid"]:
                return False
            if mine["failed_idx"] != theirs["failed_idx"]:
                return False
            if expected_type == "num":
                a = _to_float(mine["value"])
                b = _to_float(theirs["value"])
                if a is None or b is None:
                    return _norm(mine["value"]) == _norm(theirs["value"])
                return _nums_close(a, b, tol)
            return _norm(mine["value"]) == _norm(theirs["value"])

        out = None
        try:
            out = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        except gl.vm.UserError:
            out = None

        claim = self.claims[claim_id]
        claim.epoch = claim.epoch + u256(1)
        self.resolutions = self.resolutions + u256(1)

        if out is None:
            claim.status = "UNRESOLVED"
            self.facts[claim_id] = Fact(
                "", "UNRESOLVED", u256(0), u256(len(sources)), "", "", "[]", claim.epoch
            )
            return

        if out["band"] == "QUORUM":
            claim.status = "RESOLVED"
        else:
            claim.status = out["band"]

        self.facts[claim_id] = Fact(
            out["value"],
            out["band"],
            u256(out["valid"]),
            u256(out["total"]),
            out["failed_idx"],
            out["disagree_idx"],
            out["quotes"],
            claim.epoch,
        )

    @gl.public.write.payable
    def challenge(self, claim_id: str, extra_source: str):
        if claim_id not in self.claims:
            raise gl.vm.UserError("claim not found")
        claim = self.claims[claim_id]
        sources = json.loads(claim.sources_json)
        if len(sources) >= MAX_SOURCES:
            raise gl.vm.UserError("source limit reached")
        if extra_source in sources:
            raise gl.vm.UserError("source already registered")
        sources.append(extra_source)
        claim.sources_json = json.dumps(sources)
        claim.epoch = claim.epoch + u256(1)
        claim.status = "CONTESTED"
        claim.challenger = gl.message.sender_address
        claim.bond = gl.message.value

    @gl.public.view
    def get_claim(self, claim_id: str) -> str:
        if claim_id not in self.claims:
            return ""
        c = self.claims[claim_id]
        return json.dumps(
            {
                "claim_id": claim_id,
                "question": c.question,
                "sources": json.loads(c.sources_json),
                "expected_type": c.expected_type,
                "tolerance_bp": str(c.tolerance_bp),
                "min_valid_sources": str(c.min_valid_sources),
                "epoch": str(c.epoch),
                "status": c.status,
                "registrant": str(c.registrant),
                "challenger": str(c.challenger),
                "bond": str(c.bond),
            },
            sort_keys=True,
        )

    @gl.public.view
    def get_fact(self, claim_id: str) -> str:
        if claim_id not in self.facts:
            return ""
        f = self.facts[claim_id]
        return json.dumps(
            {
                "value": f.value,
                "band": f.band,
                "valid_sources": str(f.valid_sources),
                "total_sources": str(f.total_sources),
                "failed_idx": f.failed_idx,
                "disagree_idx": f.disagree_idx,
                "quotes": json.loads(f.quotes_json),
                "epoch": str(f.epoch),
            },
            sort_keys=True,
        )

    @gl.public.view
    def get_band(self, claim_id: str) -> str:
        if claim_id not in self.facts:
            return "NONE"
        return self.facts[claim_id].band

    @gl.public.view
    def is_current(self, claim_id: str) -> bool:
        if claim_id not in self.claims or claim_id not in self.facts:
            return False
        return (
            self.claims[claim_id].epoch == self.facts[claim_id].epoch
            and self.facts[claim_id].band == "QUORUM"
        )

    @gl.public.view
    def stats(self) -> str:
        return json.dumps(
            {"claims": str(len(self.claims)), "resolutions": str(self.resolutions)},
            sort_keys=True,
        )