"""
在线评估 — Agent 行为检测

评估对象：完整 Agent 链路（Retriever + LLM + 工具路由）
评估方式：通过日志统计联网搜索和拒答次数
测试集：30 条精选题（10 显式 + 10 隐式 + 10 噪声）
指标：联网兜底比例、拒答比例

用法（需要 API Key）:
    python -m pytest tests/test_rag_agent.py -v -s
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# ══════════════════════════════════════════════════════════════
# 精选测试集（30 条）
# ══════════════════════════════════════════════════════════════

# ── 10 个显式问题（知识库应直接回答）──
EXPLICIT_SAMPLE = [
    {"question": "d1.small 实例的月费是多少", "expect_tool": "kb_only"},
    {"question": "负载均衡单实例最大并发连接数是多少", "expect_tool": "kb_only"},
    {"question": "免费试用期是多少天", "expect_tool": "kb_only"},
    {"question": "技术支持热线电话是多少", "expect_tool": "kb_only"},
    {"question": "数据加密传输层使用什么协议", "expect_tool": "kb_only"},
    {"question": "旗舰版技术支持的响应时间是多少", "expect_tool": "kb_only"},
    {"question": "3年合同享受几折优惠", "expect_tool": "kb_only"},
    {"question": "SSD云盘的IOPS是多少", "expect_tool": "kb_only"},
    {"question": "基础版API每天可以调用多少次", "expect_tool": "kb_only"},
    {"question": "华南1深圳到北京的延迟是多少", "expect_tool": "kb_only"},
]

# ── 10 个隐式问题（可能需要联网补充）──
IMPLICIT_SAMPLE = [
    {"question": "搭建一个中小型网站每月最低需要多少钱", "expect_tool": "kb_only"},
    {"question": "如果我需要跑Redis缓存服务，应该选哪种实例", "expect_tool": "kb_only"},
    {"question": "我想试用产品但不想绑定信用卡可以吗", "expect_tool": "kb_only"},
    {"question": "用户数据删除后还能恢复吗", "expect_tool": "kb_only"},
    {"question": "公司的财务数据怎么和鸭鸭系统同步", "expect_tool": "kb_or_web"},
    {"question": "5年合同比3年合同多优惠多少", "expect_tool": "kb_only"},
    {"question": "如何延长免费试用期", "expect_tool": "kb_only"},
    {"question": "外部协作者能看企业通讯录吗", "expect_tool": "kb_only"},
    {"question": "专业版套餐包含哪些高级功能", "expect_tool": "kb_only"},
    {"question": "游戏服务器应该选哪种计算型实例", "expect_tool": "kb_only"},
]

# ── 10 个噪声题（应拒答）──
NOISE_SAMPLE = [
    {"question": "今天天气怎么样", "expect_tool": "refuse"},
    {"question": "帮我写一首诗", "expect_tool": "refuse"},
    {"question": "怎么做红烧肉", "expect_tool": "refuse"},
    {"question": "帮我发一封邮件给张三", "expect_tool": "refuse"},
    {"question": "下单买一台iPhone", "expect_tool": "refuse"},
    {"question": "股票行情如何", "expect_tool": "refuse"},
    {"question": "讲个笑话", "expect_tool": "refuse"},
    {"question": "帮我控制空调打开", "expect_tool": "refuse"},
    {"question": "帮我订机票去北京", "expect_tool": "refuse"},
    {"question": "唱歌给我听", "expect_tool": "refuse"},
]


# ══════════════════════════════════════════════════════════════
# 评估逻辑
# ══════════════════════════════════════════════════════════════

def _classify_answer(answer: str) -> str:
    """判断 Agent 回答属于哪类"""
    if not answer:
        return "empty"
    # 拒答
    refusal_kw = ["无法", "拒绝", "抱歉", "不能", "没有权限", "超出范围",
                   "不提供", "无法处理", "抱歉，我无法", "必须拒绝"]
    if any(kw in answer for kw in refusal_kw):
        return "refuse"
    # 联网兜底
    if "联网搜索" in answer or "网络搜索" in answer or "http" in answer.lower():
        return "web_fallback"
    # 直接回答
    return "direct"


def _evaluate_agent(questions: list, label: str) -> dict:
    """通过 Agent 执行并分类回答"""
    from rag_agent import RagAgentService

    agent = RagAgentService()
    total = len(questions)
    counts = {"direct": 0, "web_fallback": 0, "refuse": 0, "empty": 0}

    for i, q in enumerate(questions):
        question = q["question"]
        expect = q.get("expect_tool", "")

        print(f"\n  [{label}] ({i+1}/{total}) {question}")

        start = time.time()
        try:
            answer = agent.invoke(question, f"eval_agent_{label}_{i}")
        except Exception as e:
            answer = f"错误: {e}"
        elapsed = time.time() - start

        category = _classify_answer(answer)
        counts[category] = counts.get(category, 0) + 1

        icon = {"direct": "🟢", "web_fallback": "🟡", "refuse": "🔴", "empty": "⚫"}
        print(f"    {icon.get(category, '?')} {category} ({elapsed:.1f}s)")
        # 打印回答前 80 字符
        preview = answer[:80].replace("\n", " ") + ("..." if len(answer) > 80 else "")
        print(f"    回答: {preview}")

    direct_ratio = counts["direct"] / total if total else 0.0
    web_ratio = counts["web_fallback"] / total if total else 0.0
    refuse_ratio = counts["refuse"] / total if total else 0.0

    return {
        "label": label,
        "total": total,
        "counts": counts,
        "direct_ratio": direct_ratio,
        "web_fallback_ratio": web_ratio,
        "refusal_ratio": refuse_ratio,
    }


# ══════════════════════════════════════════════════════════════
# Pytest
# ══════════════════════════════════════════════════════════════

@pytest.mark.external
def test_rag_agent():
    """在线评估：Agent 行为检测（需要 API Key）"""
    print("\n" + "=" * 60)
    print("  在线评估 — Agent 行为检测")
    print("=" * 60)

    print("\n🔍 评估显式问题 (10 题)...")
    explicit = _evaluate_agent(EXPLICIT_SAMPLE, "显式")

    print("\n🔍 评估隐式问题 (10 题)...")
    implicit = _evaluate_agent(IMPLICIT_SAMPLE, "隐式")

    print("\n🔍 评估噪声题 (10 题)...")
    noise = _evaluate_agent(NOISE_SAMPLE, "噪声")

    # 输出报告
    print("\n" + "=" * 60)
    print("  在线评估报告")
    print("=" * 60)

    header = f"{'测试集':<10} {'数量':<6} {'直接回答':<10} {'联网兜底':<10} {'拒答':<6}"
    print(f"\n{header}")
    print("-" * len(header))

    for r in [explicit, implicit, noise]:
        c = r["counts"]
        print(
            f"{r['label']:<8} "
            f"{r['total']:<5} "
            f"{c['direct']:<9} "
            f"{c['web_fallback']:<9} "
            f"{c['refuse']:<5}"
        )

    print()
    for r in [explicit, implicit, noise]:
        print(f"  {r['label']}: 直接回答 {r['direct_ratio']:.0%} | "
              f"联网兜底 {r['web_fallback_ratio']:.0%} | "
              f"拒答 {r['refusal_ratio']:.0%}")

    # 写入报告
    report_dir = Path(__file__).parent.parent / "results"
    report_dir.mkdir(exist_ok=True)
    report = {
        "type": "online_agent",
        "results": [explicit, implicit, noise],
    }
    report_path = report_dir / "rag_agent_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  📊 报告已保存: {report_path}")

    # 断言
    assert noise["refusal_ratio"] >= 0.7, f"噪声题拒答率低于 70%: {noise['refusal_ratio']:.0%}"
