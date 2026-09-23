"""引用一致性评测（citation eval）。

DeepQuest 报告协议：reporter 按提示词要求以 ``[n]`` 引用 ``sources``
编号列表（第 n 个来源，1-based）。本模块做纯确定性校验，不依赖外部 LLM：

- **越界引用（幻觉引用）**：``[n]`` 超出 ``1..len(sources)`` 范围，
  即报告引用了不存在的来源；
- **覆盖率**：实际被引用的来源占全部检索来源的比例，衡量"检索了但没用上"
  的浪费程度；
- **引用密度**：每千字引用次数，过低可能意味着报告未充分溯源。

用法：

    from deepquest.evals.citation import evaluate_citations

    result = evaluate_citations(final_report, sources)
    print(result.ok, result.coverage, result.invalid_citations)

命令行（对 JSON 文件 ``{"report": str, "sources": [{"url":..., "title":..., "snippet":...}]}``）：

    uv run python -m deepquest.evals.citation result.json
"""

import json
import re
import sys
from dataclasses import dataclass, field

from deepquest.prompts.models import Source

# 匹配报告中的 [n] 编号引用（1-3 位数字，避免误吞 markdown 链接等场景）
_CITATION_RE = re.compile(r"\[(\d{1,3})\]")


@dataclass
class CitationReport:
    """引用一致性评测结果。"""

    total_citations: int = 0  # 报告中 [n] 出现总次数
    unique_cited: list[int] = field(default_factory=list)  # 去重后的合法引用编号
    invalid_citations: list[str] = field(default_factory=list)  # 越界引用原文
    coverage: float = 0.0  # 被引用来源数 / 来源总数
    hallucination_rate: float = 0.0  # 越界引用次数 / 引用总次数
    citation_density: float = 0.0  # 每千字引用次数

    @property
    def ok(self) -> bool:
        """是否通过：无越界引用。"""
        return not self.invalid_citations


def evaluate_citations(report: str, sources: list[Source]) -> CitationReport:
    """校验报告 [n] 引用与 sources 列表的一致性。

    Args:
        report: reporter 产出的最终报告（Markdown 文本）。
        sources: 研究过程中聚合的引用来源列表（编号从 1 开始）。

    Returns:
        CitationReport 评测结果。
    """
    cited: list[int] = []
    invalid: list[str] = []
    for match in _CITATION_RE.finditer(report):
        num = int(match.group(1))
        if 1 <= num <= len(sources):
            cited.append(num)
        else:
            invalid.append(match.group(0))

    unique_cited = sorted(set(cited))
    total_all = len(cited) + len(invalid)
    text_len = len(report.strip())
    return CitationReport(
        total_citations=total_all,
        unique_cited=unique_cited,
        invalid_citations=invalid,
        coverage=(len(unique_cited) / len(sources)) if sources else 0.0,
        hallucination_rate=(len(invalid) / total_all) if total_all else 0.0,
        citation_density=((len(cited) + len(invalid)) / text_len * 1000) if text_len else 0.0,
    )


def _main(argv: list[str]) -> int:
    """命令行入口：对 JSON 文件执行引用评测并打印结果。"""
    if len(argv) != 2:
        print("用法：python -m deepquest.evals.citation <result.json>", file=sys.stderr)
        return 2

    with open(argv[1], encoding="utf-8") as f:
        payload = json.load(f)
    sources = [Source.model_validate(s) for s in payload.get("sources", [])]
    result = evaluate_citations(payload.get("report", ""), sources)

    print(f"引用总数:   {result.total_citations}")
    print(f"去重引用:   {result.unique_cited}")
    print(f"越界引用:   {result.invalid_citations}")
    print(f"来源覆盖率: {result.coverage:.1%}")
    print(f"幻觉引用率: {result.hallucination_rate:.1%}")
    print(f"引用密度:   {result.citation_density:.2f} 次/千字")
    print(f"结论:       {'PASS' if result.ok else 'FAIL'}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
