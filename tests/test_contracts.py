"""Every structured AI contract must reject bad output and normalise good output."""
import pytest

from app.agent_contracts import CONTRACTS, ContractError, validate_code
from app.fallbacks import FALLBACKS


def test_every_agent_has_a_complete_contract():
    for agent_id in ("ceo", "product", "design", "backend", "database", "frontend",
                     "qa", "security", "devops", "founder"):
        contract = CONTRACTS[agent_id]
        assert contract["schema"].strip()
        assert callable(contract["validate"])
        assert contract["fallback"] in FALLBACKS


def test_validators_raise_on_empty_required_fields():
    with pytest.raises(ContractError):
        CONTRACTS["ceo"]["validate"]({"summary": "", "features": []})
    with pytest.raises(ContractError):
        CONTRACTS["design"]["validate"]({"design_system": "fine", "pages": []})
    with pytest.raises(ContractError):
        CONTRACTS["backend"]["validate"]({"architecture": "x", "endpoints": []})


def test_analysis_validator_normalises_and_clamps():
    payload = CONTRACTS["ceo"]["validate"]({
        "summary": "  an online shop  ",
        "features": ["login", "cart", {"weird": "object"}],
        "entities": ["users", {"name": "orders", "fields": ["id"]}],
        "risks": "one risk\nanother risk",
    })
    assert payload["summary"] == "an online shop"
    assert payload["features"][0] == "login"
    assert payload["entities"][0] == {"name": "users", "fields": []}
    assert payload["entities"][1]["name"] == "orders"
    assert len(payload["risks"]) == 2


def test_api_plan_validator_forces_absolute_paths_and_valid_methods():
    payload = CONTRACTS["backend"]["validate"]({
        "architecture": "Express",
        "endpoints": ["GET api/products", {"method": "delete", "path": "orders/1", "auth": True}],
    })
    assert payload["endpoints"][0]["path"] == "/api/products"
    assert payload["endpoints"][1]["method"] == "DELETE"
    assert payload["endpoints"][1]["path"] == "/orders/1"


def test_code_validator_rejects_unsafe_paths_and_fenced_content():
    with pytest.raises(ContractError):
        validate_code({"path": "../escape.js", "content": "x"})
    with pytest.raises(ContractError):
        validate_code({"path": "/etc/passwd", "content": "x"})
    with pytest.raises(ContractError):
        validate_code({"path": "ok.js", "content": ""})
    with pytest.raises(ContractError):
        validate_code({"path": "ok.js", "content": "```js\nx\n```"})
    good = validate_code({"path": "src/app.js", "content": "export const a = 1;\n"})
    assert good["path"] == "src/app.js"


def test_deterministic_fallbacks_satisfy_their_own_contracts():
    requirement = "Build an online shopping platform with cart and checkout"
    for agent_id, contract in CONTRACTS.items():
        fallback = FALLBACKS[contract["fallback"]]
        payload = fallback(requirement)
        # The fallback output must pass the same validator the AI output must pass.
        contract["validate"](payload)


def test_security_and_test_reports_are_derived_from_real_results():
    report = FALLBACKS["testReportFallback"]("req", {"passed": 59, "failed": 0})
    assert report["verdict"] == "passed"
    failing = FALLBACKS["testReportFallback"]("req", {"passed": 58, "failed": 1})
    assert failing["verdict"] == "failed"

    clean = FALLBACKS["securityReportFallback"]("req", {"findings": [], "checks": []})
    assert clean["verdict"] == "passed"
    risky = FALLBACKS["securityReportFallback"](
        "req", {"findings": [{"severity": "critical", "title": "key"}], "checks": []})
    assert risky["verdict"] == "blocked"
