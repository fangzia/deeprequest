"""引用一致性评测（citation eval）单测：覆盖合法/越界/空场景与 CLI。"""

import json

from deepquest.evals.citation import CitationReport, evaluate_citations
from deepquest.prompts.models import Source


def _sources(n: int) -> list[Source]:
    return [Source(url=f"https://example.com/{i}", title=f"来源{i}") for i in range(1, n + 1)]


def test_all_valid_citations_pass():
    """全部引用命中来源范围时 PASS，覆盖率与去重正确。"""
    sources = _sources(3)
    report = "结论甲[1]，结论乙[2]，再次强调[1]，结论丙[3]。"
    result = evaluate_citations(report, sources)
    assert result.ok
    assert result.total_citations == 4
    assert result.unique_cited == [1, 2, 3]
    assert result.coverage == 1.0
    assert result.hallucination_rate == 0.0


def test_out_of_range_citation_fails():
    """越界引用（如 [5]）被识别为幻觉引用并 FAIL。"""
    sources = _sources(3)
    report = "正常引用[1]，越界引用[5]，又越界[99]。"
    result = evaluate_citations(report, sources)
    assert not result.ok
    assert result.invalid_citations == ["[5]", "[99]"]
    assert result.unique_cited == [1]
    assert result.hallucination_rate > 0.5


def test_zero_index_is_invalid():
    """[0] 不是合法编号（来源编号从 1 开始）。"""
    result = evaluate_citations("引用[0]", _sources(2))
    assert not result.ok
    assert result.invalid_citations == ["[0]"]


def test_coverage_counts_uncited_sources():
    """检索到但未引用的来源会拉低覆盖率。"""
    sources = _sources(4)
    result = evaluate_citations("只引用了[1]", sources)
    assert result.ok
    assert result.coverage == 0.25


def test_empty_sources_with_citations():
    """无来源却有引用：全部记为越界引用。"""
    result = evaluate_citations("没有任何来源的引用[1]", [])
    assert not result.ok
    assert result.invalid_citations == ["[1]"]


def test_empty_report():
    """空报告不崩溃，指标全部归零。"""
    result = evaluate_citations("", _sources(2))
    assert result.ok
    assert result.total_citations == 0
    assert result.coverage == 0.0


def test_markdown_links_not_counted():
    """markdown 链接 [文本](url) 不应被计为编号引用（文本非纯数字）。"""
    result = evaluate_citations("参见 [DeepSeek](https://deepseek.com) 文档[1]", _sources(1))
    assert result.ok
    assert result.total_citations == 1


def test_cli_pass_and_exit_code(tmp_path, monkeypatch, capsys):
    """CLI 入口：合法输入打印 PASS 且退出码 0。"""
    from deepquest.evals.citation import _main

    payload = {"report": "引用[1]", "sources": [{"url": "https://a.com", "title": "A"}]}
    path = tmp_path / "result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _main(["prog", str(path)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_cli_fail_exit_code(tmp_path, capsys):
    """CLI 入口：越界引用打印 FAIL 且退出码 1。"""
    from deepquest.evals.citation import _main

    payload = {"report": "引用[3]", "sources": [{"url": "https://a.com", "title": "A"}]}
    path = tmp_path / "result.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _main(["prog", str(path)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_citation_report_ok_property():
    """CitationReport.ok 语义：无越界引用即通过。"""
    assert CitationReport(invalid_citations=[]).ok
    assert not CitationReport(invalid_citations=["[9]"]).ok
