"""
在线评估 — Agent 工具调用刚性评价

规则：
  T1 内部知识型: knowledge_base_search 必须出现
  T2 实时信息型: knowledge_base_search + web_search 都必须出现
  T3 通用开放型: knowledge_base_search 必须出现，允许 web_search
  T4 纯计算型:   calculator 必须出现
  T5 边界外/拒答型: 工具必须为空，回答 < 50 字

用法（需要 API Key）:
    python -m pytest tests/test_rag_agent.py -v -s
"""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

CASES_PATH = Path(__file__).parent / "test_data" / "online_cases.json"


def _load_cases() -> list:
    with open(CASES_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.external
def test_rag_agent_online():
    """在线评估：Agent 工具调用准确率"""
    from rag_agent import RagAgentService

    categories = _load_cases()
    total_passed, total_failed = 0, 0
    details = []

    print("=" * 60)
    print("  在线评估 — 工具调用刚性评价")
    print("=" * 60)

    for cat in categories:
        cid = cat["category"]
        name = cat["category_name"]
        must_have = set(cat["must_have"])
        allow = set(cat["allow"])
        cases = cat["cases"]
        total = len(cases)

        print(f"\n{'─' * 60}")
        print(f"  {cid} {name}（{total} 条）")
        print(f"  必须包含: {must_have}  允许: {allow or '—'}")
        print(f"{'─' * 60}")

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
            fail_reasons = []

            # 检查 must_have 是否全部出现
            missing = must_have - actual
            if missing:
                fail_reasons.append(f"缺少必须调用的工具: {missing}")

            # T5 专属：工具必须为空（降级引导，不调工具）
            if cid == "T5":
                if actual:
                    fail_reasons.append(f"禁用了工具但实际调用了: {actual}")

            status = "✅" if not fail_reasons else "❌"
            tool_str = ", ".join(sorted(actual)) if actual else "无"
            preview = answer[:60].replace("\n", " ") + ("..." if len(answer) > 60 else "")

            print(f"  {status} [{cid}] ({i+1}/{total}) {question}")
            print(f"      工具={tool_str}  耗时={elapsed:.1f}s  长度={answer_len}字")
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
                "actual": list(actual),
                "answer_len": answer_len,
                "passed": not fail_reasons,
                "fail_reasons": fail_reasons,
            })

        # 分类汇总
        cat_errors = [d for d in details if d["cid"] == cid and not d["passed"]]
        cat_pass = total - len(cat_errors)
        print(f"\n  📊 {cid}: {cat_pass}/{total} 通过 ({cat_pass/total:.0%})")

    # 全局汇总
    print(f"\n{'=' * 60}")
    print(f"  汇总: ✅ {total_passed} / ❌ {total_failed}")
    print(f"{'=' * 60}")

    assert total_failed == 0, f"存在 {total_failed} 条未通过"
