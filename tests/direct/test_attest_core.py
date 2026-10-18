import json

GOOD_A = "registry says: version is 1.3.0 (latest)"
GOOD_B = "mirror says: version is 1.3.0 (latest)"
BAD_B = "mirror says: nothing relevant here"
BODY_2_0 = "mirror says: version is 2.0.0"
LLM_OK = json.dumps({"found": True, "value": "1.3.0", "quote": "version is 1.3.0"})
LLM_2_0 = json.dumps({"found": True, "value": "2.0.0", "quote": "version is 2.0.0"})

SRC_AB = ["https://a.example.com/p", "https://b.example.com/p"]


def _setup(direct_vm, direct_deploy, b_body=GOOD_B, b_llm=None):
    direct_vm.mock_web(r".*a\.example\.com.*", {"status": 200, "body": GOOD_A})
    direct_vm.mock_web(r".*b\.example\.com.*", {"status": 200, "body": b_body})
    if b_llm is not None:
        direct_vm.mock_llm(r"(?s).*mirror says.*", b_llm)
    direct_vm.mock_llm(r".*", LLM_OK)
    direct_vm.check_pickling = True
    return direct_deploy("contracts/attest_core.py")


def _reg(contract, cid="c1", sources=None, minv=2):
    contract.register_claim(
        cid, "What is the version?", sources or SRC_AB, "str", 100, minv
    )


def test_register_and_read(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy)
    direct_vm.sender = direct_alice
    _reg(c)
    data = json.loads(c.get_claim("c1"))
    assert data["status"] == "OPEN"
    assert data["epoch"] == "0"
    assert len(data["sources"]) == 2


def test_register_duplicate_reverts(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy)
    direct_vm.sender = direct_alice
    _reg(c)
    with direct_vm.expect_revert("claim_id already exists"):
        _reg(c)


def test_register_bad_json_reverts(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("not valid JSON"):
        c.register_claim("c1", "q", "{oops", "str", 100, 2)


def test_register_min_out_of_range(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("min_valid_sources out of range"):
        c.register_claim("c1", "q", '["https://a.example.com/p"]', "str", 100, 3)


def test_resolve_reaches_quorum(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy)
    direct_vm.sender = direct_alice
    _reg(c)
    c.resolve("c1")
    f = json.loads(c.get_fact("c1"))
    assert f["band"] == "QUORUM"
    assert f["value"] == "1.3.0"
    assert f["valid_sources"] == "2"
    assert f["failed_idx"] == ""
    assert c.is_current("c1") is True


def test_unresolved_when_a_source_is_ungrounded(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy, b_body=BAD_B)
    direct_vm.sender = direct_alice
    _reg(c)
    c.resolve("c1")
    f = json.loads(c.get_fact("c1"))
    assert f["band"] == "UNRESOLVED"
    assert f["failed_idx"] == "1"
    assert f["valid_sources"] == "1"
    assert f["value"] == ""
    assert c.is_current("c1") is False


def test_contested_when_sources_disagree(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy, b_body=BODY_2_0, b_llm=LLM_2_0)
    direct_vm.sender = direct_alice
    _reg(c)
    c.resolve("c1")
    f = json.loads(c.get_fact("c1"))
    assert f["band"] == "CONTESTED"
    assert c.is_current("c1") is False


def test_validator_rejects_when_value_differs(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy)
    direct_vm.sender = direct_alice
    _reg(c)
    c.resolve("c1")
    direct_vm.clear_mocks()
    direct_vm.mock_web(r".*a\.example\.com.*", {"status": 200, "body": GOOD_A})
    direct_vm.mock_web(r".*b\.example\.com.*", {"status": 200, "body": GOOD_B})
    direct_vm.mock_llm(
        r".*", json.dumps({"found": True, "value": "9.9.9", "quote": "version is 1.3.0"})
    )
    assert direct_vm.run_validator() is False


def test_challenge_marks_contested_and_bumps_epoch(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    c = _setup(direct_vm, direct_deploy)
    direct_vm.sender = direct_alice
    _reg(c)
    direct_vm.sender = direct_bob
    c.challenge("c1", "https://c.example.com/p")
    data = json.loads(c.get_claim("c1"))
    assert data["status"] == "CONTESTED"
    assert data["epoch"] == "1"
    assert len(data["sources"]) == 3


def test_challenge_rejects_duplicate_source(direct_vm, direct_deploy, direct_alice):
    c = _setup(direct_vm, direct_deploy)
    direct_vm.sender = direct_alice
    _reg(c)
    with direct_vm.expect_revert("source already registered"):
        c.challenge("c1", SRC_AB[0])