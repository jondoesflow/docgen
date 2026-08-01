"""Cost estimation for LLM usage reporting."""

from docgen.llm.pricing import estimate_cost, rates_for, usage_summary_line


def test_rates_for_known_models():
    assert rates_for("claude-sonnet-4-6") == (3.00, 15.00)
    assert rates_for("claude-opus-5") == (5.00, 25.00)
    assert rates_for("claude-haiku-4-5") == (1.00, 5.00)


def test_rates_match_dated_variants_by_prefix():
    assert rates_for("claude-haiku-4-5-20251001") == (1.00, 5.00)


def test_unknown_model_returns_none():
    assert rates_for("claude-mystery-9") is None
    assert estimate_cost("claude-mystery-9", 1000, 1000) is None


def test_estimate_cost_math():
    # 1M input + 1M output on sonnet-4-6 = $3 + $15
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000) == 18.00
    # typical docgen run: 50k in, 5k out on sonnet-4-6 = 0.15 + 0.075
    assert round(estimate_cost("claude-sonnet-4-6", 50_000, 5_000), 4) == 0.225


def test_summary_line_with_cost():
    line = usage_summary_line("claude-sonnet-4-6", 7, 50_000, 5_000)
    assert "7 call(s)" in line
    assert "50,000 input + 5,000 output" in line
    assert "$0.2250 USD" in line


def test_summary_line_unknown_model():
    line = usage_summary_line("claude-mystery-9", 1, 100, 100)
    assert "pricing unknown" in line


def test_render_reports_cost_when_llm_used(built_fixtures, tmp_path, capsys):
    """End-of-run summary appears when the narrative provider carries a used client."""
    from docgen.commands import render_documents
    from docgen.config import DocgenConfig
    from docgen.parsers import parse_solution
    import docgen.llm

    class FakeClientWithUsage:
        model = "claude-sonnet-4-6"
        calls = 0
        total_input_tokens = 0
        total_output_tokens = 0

        def complete(self, purpose, system, user):
            FakeClientWithUsage.calls += 1
            FakeClientWithUsage.total_input_tokens += 10_000
            FakeClientWithUsage.total_output_tokens += 500
            return "Narrative about the abc_project table."

    def fake_factory(snapshot, cfg, out_dir):
        client = FakeClientWithUsage()

        def provider(purpose, payload):
            return client.complete(purpose, "", "")

        provider.client = client
        return provider

    snapshot = parse_solution(built_fixtures / "rich.zip")
    original = docgen.llm.make_narrative_provider
    docgen.llm.make_narrative_provider = fake_factory
    try:
        render_documents(snapshot, ["hld"], ["md"], tmp_path, DocgenConfig(), no_llm=False)
    finally:
        docgen.llm.make_narrative_provider = original

    out = capsys.readouterr().out
    assert "LLM usage:" in out
    assert "estimated cost $" in out
