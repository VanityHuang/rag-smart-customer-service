"""
在线评估 — Agent 行为检测（基于工具调用的刚性评价）

指标一（工具调用准确率 - 刚性红线）：
  实际调用的工具名称集合必须严格等于预期集合（T1/T2）
  或包含于预期集合（T3），或为空（T4）。

指标二（强制拒答空转测试 - T4专属）：
  预期工具为空时，必须 tool_calls 为空 且 response < 50 字。

指标三（禁止幻觉回流 - T1专属）：
  检测到 tool_calls 包含 web_search，直接判 FAIL。

通过阈值：
  T1: web_search 误召率 < 5%（15 条中最多 1 条犯错）
  T2: web_search 漏召率 = 0%
  T4: 工具误调率 = 0%，长文本废话率 = 0%

用法（需要 API Key）:
    python -m pytest tests/test_rag_agent.py -v -s
"""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent / "test_data"
CASES_PATH = DATA_DIR / "online_cases.json"


def _load_cases() -> list:
    """从 JSON 加载测试用例"""
    with open(CASES_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.external
def test_rag_agent_online():
    """在线评估：Agent 行为检测"""
    from rag_agent import RagAgentService

    categories = _load_cases()
    total_passed = 0
    total_failed = 0
    details = []

    print("=" * 60)
    print("  在线评估 — 工具调用准确率")
    print("=" * 60)

    for cat in categories:
        cid = cat["category"]
        name = cat["category_name"]
        expected = set(cat["expected_tools"])
        cases = cat["cases"]
        total = len(cases)

        print(f"\n{'─' * 60}")
        print(f"  {cid} {name}（{total} 条）")
        print(f"  预期工具: {expected}")
        print(f"{'─' * 60}")

        errors = []
        for i, case in enumerate(cases):
            question = case["question"]

            agent = RagAgentService()
            start = time.time()
            try:
                answer = agent.invoke(question, f"eval_{cid}_{i}")
            except Exception as e:
                answer = f"错误: {e}"
            elapsed = time.time() - start

            actual = agent.tools_called
            answer_len = len(answer.strip())

            # ── 逐条判定 ──
            fail_reasons = []

            # 指标一：工具调用准确率
            if cid in ("T1", "T2"):
                if actual != expected:
                    fail_reasons.append(
                        f"工具不匹配: 实际={actual}, 预期={expected}"
                    )
            elif cid == "T3":
                if not actual.issubset(expected):
                    fail_reasons.append(
                        f"工具不在预期范围内: 实际={actual}, 预期={expected}"
                    )
            elif cid == "T4":
                if actual != expected:
                    fail_reasons.append(
                        f"工具不匹配: 实际={actual}, 预期={expected}"
                    )

            # 指标二：T4 拒答长度
            if cid == "T4" and answer_len >= 50:
                fail_reasons.append(
                    f"拒答过长: {answer_len} 字（上限 50）"
                )

            # 指标三：T1 禁止幻觉回流
            if cid == "T1" and "web_search" in actual:
                fail_reasons.append(
                    "🔴 告警：内部知识型问题泄漏到 web_search！"
                )

            status = "✅" if not fail_reasons else "❌"
            tool_str = ", ".join(sorted(actual)) if actual else "无"
            preview = answer[:60].replace("\n", " ") + ("..." if len(answer) > 60 else "")

            print(f"  {status} [{cid}] ({i+1}/{total}) {question}")
            print(f"      工具={tool_str} 耗时={elapsed:.1f}s 长度={answer_len}字")
            if fail_reasons:
                for r in fail_reasons:
                    print(f"      ⚠️  {r}")
                print(f"      回答: {preview}")

            if not fail_reasons:
                total_passed += 1
            else:
                total_failed += 1

            details.append({
                "cid": cid,
                "question": question,
                "expected": list(expected),
                "actual": list(actual),
                "answer_len": answer_len,
                "passed": not fail_reasons,
                "fail_reasons": fail_reasons,
            })

        # ── 分类汇总 ──
        cat_errors = [d for d in details if d["cid"] == cid and not d["passed"]]
        cat_total = len(cases)
        cat_pass = cat_total - len(cat_errors)
        print(f"\n  📊 {cid}: 通过 {cat_pass}/{cat_total} ({cat_pass/cat_total:.0%})")
        if cat_errors:
            print(f"     失败项: {[e['question'][:20] + '...' for e in cat_errors]}")

    # ── 全局汇总 ──
    print(f"\n{'=' * 60}")
    print(f"  汇总: ✅ {total_passed} / ❌ {total_failed}")
    print(f"{'=' * 60}")

    # ── 断言 ──
    assert total_failed == 0, f"存在 {total_failed} 条未通过"
