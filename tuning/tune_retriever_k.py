"""
retriever_k 调优 — 离线扫描 + 在线验证

Phase 1（离线）: 循环 k=1,3,5,7,10，绘制 Hit Rate 收敛曲线，锁定拐点候选
Phase 2（在线）: 对候选 k 值运行真实 Agent 调用，对比 Token 消耗与回答质量

前提: 已通过 tune_chunk_params.py 确定了最优 chunk_size 和 overlap

用法:
    # Phase 1: 离线扫描（无需 API Key，快速）
    python tune_retriever_k.py --phase offline

    # Phase 2: 在线验证（需要 API Key，较慢）
    python tune_retriever_k.py --phase online --k 3 5 7

    # 全量执行
    python tune_retriever_k.py
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "tests" / "data"

SEED_FILES = [
    "鸭鸭云服务器产品规格.md",
    "鸭鸭科技常见问题手册.txt",
    "鸭鸭科技员工手册.docx",
    "鸭鸭服务器运维手册.pdf",
    "鸭鸭科技业务报告.png",
]

# 70 题测试集（内联）
EXPLICIT_QUESTIONS = [
    {"question": "d1.small 实例的月费是多少", "expected": "99"},
    {"question": "d1.xlarge 有多少核CPU", "expected": "8 核"},
    {"question": "GPU型实例 g1.xlarge 配置了几个A10 GPU", "expected": "4×A10"},
    {"question": "SSD云盘的IOPS是多少", "expected": "20,000"},
    {"question": "超高IOPS盘的吞吐量是多少", "expected": "4,000 MB/s"},
    {"question": "对象存储中归档存储的单价是多少", "expected": "0.03"},
    {"question": "100Mbps公网带宽的月费是多少", "expected": "2000"},
    {"question": "负载均衡单实例最大并发连接数是多少", "expected": "500 万"},
    {"question": "DDoS高防最高防护能力是多少Gbps", "expected": "300 Gbps"},
    {"question": "旗舰版技术支持的响应时间是多少", "expected": "15 分钟"},
    {"question": "鸭鸭科技提供哪三大核心产品线", "expected": "鸭鸭 ERP"},
    {"question": "SaaS云端部署的起步价是多少", "expected": "9800 元/年/10 用户"},
    {"question": "免费试用期是多少天", "expected": "14 天"},
    {"question": "技术支持热线电话是多少", "expected": "400-800-9966"},
    {"question": "数据存储在阿里云哪个区域", "expected": "华东2（上海）"},
    {"question": "数据加密传输层使用什么协议", "expected": "TLS 1.3"},
    {"question": "基础版API每天可以调用多少次", "expected": "1000 次/天"},
    {"question": "3年合同享受几折优惠", "expected": "8 折"},
    {"question": "忘记密码后重置链接有效期是多久", "expected": "30 分钟"},
    {"question": "账号注销冷静期是多少天", "expected": "7 天"},
    {"question": "内存型实例m1.large的内存是多少", "expected": "32 GB"},
    {"question": "专业版技术支持的服务时间是什么", "expected": "工作日 8-22"},
    {"question": "高效云盘的容量范围是多少", "expected": "20-32,768 GB"},
    {"question": "对象存储深度归档的年访问率要求是多少", "expected": "不到 1%"},
    {"question": "华南1深圳到北京的延迟是多少", "expected": "25ms"},
    {"question": "旗舰版API每天可以调用多少次", "expected": "100000 次/天"},
    {"question": "专业版套餐包含多少用户", "expected": "50 用户"},
    {"question": "预置集成了哪些即时通讯系统", "expected": "钉钉/企业微信/飞书"},
    {"question": "备份数据保留多少天", "expected": "90 天"},
    {"question": "数据加密存储层使用什么加密方式", "expected": "AES-256"},
]

IMPLICIT_QUESTIONS = [
    {"question": "搭建一个中小型网站每月最低需要多少钱", "expected": "199"},
    {"question": "如果我需要跑Redis缓存服务，应该选哪种实例", "expected": "m1.medium"},
    {"question": "我想做AI推理但预算有限，推荐哪种GPU实例", "expected": "g1.medium"},
    {"question": "ddos攻击防护免费版能防多少流量", "expected": "5 Gbps"},
    {"question": "我想试用产品但不想绑定信用卡可以吗", "expected": "14 天免费试用，无需绑定信用卡"},
    {"question": "公司的财务数据怎么和鸭鸭系统同步", "expected": "金蝶/用友"},
    {"question": "用户数据删除后还能恢复吗", "expected": "数据删除后不可恢复"},
    {"question": "员工忘记密码怎么处理", "expected": "登录页点击忘记密码"},
    {"question": "如果API调用超限了会怎样", "expected": "返回 HTTP 429 状态码，次日重置"},
    {"question": "5年合同比3年合同多优惠多少", "expected": "7 折 vs 8 折"},
    {"question": "香港服务器到大陆延迟大概多少", "expected": "35ms"},
    {"question": "高并发内存数据库应该选哪种规格", "expected": "d1.2xlarge"},
    {"question": "负载均衡支持哪些层级的协议", "expected": "四层（TCP/UDP）和七层（HTTP/HTTPS）"},
    {"question": "企业应用中等流量网站推荐什么配置", "expected": "d1.large"},
    {"question": "如何延长免费试用期", "expected": "联系销售可申请延长至 30 天"},
    {"question": "电子发票多久能收到", "expected": "付款后 3 个工作日内"},
    {"question": "外部协作者能看企业通讯录吗", "expected": "不可查看企业通讯录"},
    {"question": "专业版套餐包含哪些高级功能", "expected": "高级分析和自动化"},
    {"question": "哪些地方部署了鸭鸭云服务器节点", "expected": "华北1（北京）"},
    {"question": "游戏服务器应该选哪种计算型实例", "expected": "c1.xlarge"},
]

NOISE_QUESTIONS = [
    {"question": "今天天气怎么样", "expected": ""},
    {"question": "帮我写一首诗", "expected": ""},
    {"question": "怎么做红烧肉", "expected": ""},
    {"question": "推荐一部好看的电影", "expected": ""},
    {"question": "1+1等于几", "expected": ""},
    {"question": "你好", "expected": ""},
    {"question": "谢谢", "expected": ""},
    {"question": "你是谁", "expected": ""},
    {"question": "帮我发一封邮件给张三", "expected": ""},
    {"question": "下单买一台iPhone", "expected": ""},
    {"question": "帮我订机票去北京", "expected": ""},
    {"question": "股票行情如何", "expected": ""},
    {"question": "最近有什么新闻", "expected": ""},
    {"question": "讲个笑话", "expected": ""},
    {"question": "翻译这句话成英文", "expected": ""},
    {"question": "明天星期几", "expected": ""},
    {"question": "怎么减肥", "expected": ""},
    {"question": "推荐一本好书", "expected": ""},
    {"question": "唱歌给我听", "expected": ""},
    {"question": "帮我控制空调打开", "expected": ""},
]

ALL_QUESTIONS = (
    [("显式", q) for q in EXPLICIT_QUESTIONS]
    + [("隐式", q) for q in IMPLICIT_QUESTIONS]
    + [("噪声", q) for q in NOISE_QUESTIONS]
)

# ── 在线评估精选集（30 题）──
ONLINE_SAMPLE = [
    ("显式", {"question": "d1.small 实例的月费是多少"}),
    ("显式", {"question": "负载均衡单实例最大并发连接数是多少"}),
    ("显式", {"question": "免费试用期是多少天"}),
    ("显式", {"question": "技术支持热线电话是多少"}),
    ("显式", {"question": "数据加密传输层使用什么协议"}),
    ("显式", {"question": "旗舰版技术支持的响应时间是多少"}),
    ("显式", {"question": "3年合同享受几折优惠"}),
    ("显式", {"question": "SSD云盘的IOPS是多少"}),
    ("显式", {"question": "基础版API每天可以调用多少次"}),
    ("显式", {"question": "华南1深圳到北京的延迟是多少"}),
    ("隐式", {"question": "搭建一个中小型网站每月最低需要多少钱"}),
    ("隐式", {"question": "如果我需要跑Redis缓存服务，应该选哪种实例"}),
    ("隐式", {"question": "我想试用产品但不想绑定信用卡可以吗"}),
    ("隐式", {"question": "用户数据删除后还能恢复吗"}),
    ("隐式", {"question": "公司的财务数据怎么和鸭鸭系统同步"}),
    ("隐式", {"question": "5年合同比3年合同多优惠多少"}),
    ("隐式", {"question": "如何延长免费试用期"}),
    ("隐式", {"question": "外部协作者能看企业通讯录吗"}),
    ("隐式", {"question": "专业版套餐包含哪些高级功能"}),
    ("隐式", {"question": "游戏服务器应该选哪种计算型实例"}),
    ("噪声", {"question": "今天天气怎么样"}),
    ("噪声", {"question": "帮我写一首诗"}),
    ("噪声", {"question": "怎么做红烧肉"}),
    ("噪声", {"question": "帮我发一封邮件给张三"}),
    ("噪声", {"question": "下单买一台iPhone"}),
    ("噪声", {"question": "股票行情如何"}),
    ("噪声", {"question": "讲个笑话"}),
    ("噪声", {"question": "帮我控制空调打开"}),
    ("噪声", {"question": "帮我订机票去北京"}),
    ("噪声", {"question": "唱歌给我听"}),
]


# ══════════════════════════════════════════════════════════════
# Phase 1: 离线扫描
# ══════════════════════════════════════════════════════════════

def _build_index(tmp_dir: str):
    """用当前 config 中的 chunk_size/overlap 建索引"""
    import config_data as config
    from langchain_chroma import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from file_parser import parse_bytes

    embedding = DashScopeEmbeddings(model=config.embedding_model_name)
    chroma = Chroma(
        collection_name="k_tune_test",
        embedding_function=embedding,
        persist_directory=tmp_dir,
        collection_metadata={"hnsw:space": "cosine"},
    )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        separators=config.separators,
        length_function=len,
    )

    for filename in SEED_FILES:
        fpath = DATA_DIR / filename
        if not fpath.exists():
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        if not text or len(text) < 10:
            file_bytes = fpath.read_bytes()
            text = parse_bytes(file_bytes, filename)
        if not text:
            continue
        chunks = splitter.split_text(text) if len(text) > config.min_split_char_number else [text]
        chroma.add_texts(chunks, metadatas=[{"source": filename}] * len(chunks))

    return chroma


def _evaluate_at_k(chroma, k: int) -> dict:
    """在指定 k 值下评估"""
    hits = 0
    reciprocal_ranks = []
    similarities = []

    for label, q in ALL_QUESTIONS:
        question = q["question"]
        expected = q["expected"]

        results = chroma.similarity_search_with_score(question, k=k)
        if results:
            best_similarity = 1 - results[0][1]
            similarities.append(best_similarity)

            hit = False
            best_rank = None
            for rank, (doc, score) in enumerate(results, start=1):
                if expected and expected in doc.page_content:
                    hit = True
                    if best_rank is None:
                        best_rank = rank
            if hit:
                hits += 1
                reciprocal_ranks.append(1.0 / best_rank)
            else:
                reciprocal_ranks.append(0.0)
        else:
            similarities.append(0.0)
            reciprocal_ranks.append(0.0)

    total = len(ALL_QUESTIONS)
    return {
        "k": k,
        "hit_rate": hits / total,
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
        "avg_similarity": sum(similarities) / len(similarities),
    }


def phase_offline():
    """Phase 1: 离线扫描不同 k 值"""
    import tempfile

    k_values = [1, 3, 5, 7, 10]
    results = []

    print("=" * 60)
    print("  Phase 1: 离线扫描 — Hit Rate 收敛曲线")
    print(f"  k 值范围: {k_values}")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("\n📦 构建索引...")
        chroma = _build_index(tmp_dir)
        chunk_count = len(chroma.get()["ids"])
        print(f"   索引完成: {chunk_count} 个 chunks")

        for k in k_values:
            print(f"\n🔍 评估 k={k}...")
            start = time.time()
            result = _evaluate_at_k(chroma, k)
            elapsed = time.time() - start
            results.append(result)
            print(f"   Hit Rate={result['hit_rate']:.0%}  "
                  f"MRR={result['mrr']:.2%}  "
                  f"相似度={result['avg_similarity']:.4f}  "
                  f"({elapsed:.1f}s)")

    # 输出收敛曲线（ASCII 图）
    print("\n" + "=" * 60)
    print("  Hit Rate 收敛曲线")
    print("=" * 60)

    max_bar = 40
    max_hr = max(r["hit_rate"] for r in results) if results else 1

    print(f"\n{'k':<5} {'Hit Rate':<10} {'曲线'}")
    print("-" * 60)
    for r in results:
        bar_len = int(r["hit_rate"] / max(max_hr, 0.01) * max_bar)
        bar = "█" * bar_len + "░" * (max_bar - bar_len)
        print(f"{r['k']:<5} {r['hit_rate']:<9.0%} {bar}")

    # 输出对比表
    print(f"\n{'k':<5} {'Hit Rate':<10} {'MRR':<10} {'平均相似度':<12}")
    print("-" * 45)
    for r in results:
        print(f"{r['k']:<5} {r['hit_rate']:<9.0%} {r['mrr']:<9.2%} {r['avg_similarity']:<11.4f}")

    # 找拐点：Hit Rate 增量 < 5% 的第一个 k
    candidates = []
    for i in range(1, len(results)):
        delta = results[i]["hit_rate"] - results[i - 1]["hit_rate"]
        if delta < 0.05:  # 增量小于 5%
            candidates.append(results[i]["k"])
            break
    if not candidates:
        candidates = [results[-1]["k"]]

    # 也把 Hit Rate 最高的 k 加入候选
    best_hr = max(results, key=lambda x: x["hit_rate"])
    if best_hr["k"] not in candidates:
        candidates.append(best_hr["k"])

    print(f"\n🎯 拐点候选 k 值: {candidates}")
    print(f"   (Hit Rate 增量 < 5% 的第一个 k，以及 Hit Rate 最高的 k)")

    return results, candidates


# ══════════════════════════════════════════════════════════════
# Phase 2: 在线验证
# ══════════════════════════════════════════════════════════════

def _classify_answer(answer: str) -> str:
    if not answer:
        return "empty"
    refusal_kw = ["无法", "拒绝", "抱歉", "不能", "没有权限", "超出范围",
                   "不提供", "无法处理", "抱歉，我无法", "必须拒绝"]
    if any(kw in answer for kw in refusal_kw):
        return "refuse"
    if "联网搜索" in answer or "网络搜索" in answer or "http" in answer.lower():
        return "web_fallback"
    return "direct"


def phase_online(k_values: list):
    """Phase 2: 在线验证候选 k 值"""
    import config_data as config
    from rag_agent import RagAgentService

    print("\n" + "=" * 60)
    print("  Phase 2: 在线验证 — Token 消耗 + 回答质量")
    print(f"  候选 k 值: {k_values}")
    print("=" * 60)

    results = []

    for k in k_values:
        print(f"\n{'─' * 40}")
        print(f"  测试 k={k}")
        print(f"{'─' * 40}")

        # 临时修改 config 中的 retriever_k
        original_k = config.retriever_k
        config.retriever_k = k

        agent = RagAgentService()
        total_tokens_in = 0
        total_tokens_out = 0
        categories = {"direct": 0, "web_fallback": 0, "refuse": 0}
        total = len(ONLINE_SAMPLE)

        for i, (label, q) in enumerate(ONLINE_SAMPLE):
            question = q["question"]
            print(f"  [{label}] ({i+1}/{total}) {question}", end=" ")

            start = time.time()
            try:
                answer = agent.invoke(question, f"kune_k{k}_{i}")
            except Exception as e:
                answer = f"错误: {e}"
            elapsed = time.time() - start

            # 累加 token
            usage = agent.token_usage
            total_tokens_in += usage["input_tokens"]
            total_tokens_out += usage["output_tokens"]

            category = _classify_answer(answer)
            categories[category] = categories.get(category, 0) + 1

            icon = {"direct": "🟢", "web_fallback": "🟡", "refuse": "🔴"}
            print(f"{icon.get(category, '?')} {category} ({elapsed:.1f}s)")

        # 恢复 config
        config.retriever_k = original_k

        avg_tokens_in = total_tokens_in / total
        avg_tokens_out = total_tokens_out / total
        avg_tokens_total = (total_tokens_in + total_tokens_out) / total

        result = {
            "k": k,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "avg_tokens_in": avg_tokens_in,
            "avg_tokens_out": avg_tokens_out,
            "avg_tokens_total": avg_tokens_total,
            "categories": categories,
            "direct_ratio": categories["direct"] / total,
            "web_ratio": categories["web_fallback"] / total,
            "refuse_ratio": categories["refuse"] / total,
        }
        results.append(result)

        print(f"\n  📊 k={k}: 平均 Token={avg_tokens_total:.0f} "
              f"(入{avg_tokens_in:.0f}/出{avg_tokens_out:.0f}) | "
              f"直接={categories['direct']}/{total} | "
              f"联网={categories['web_fallback']}/{total} | "
              f"拒答={categories['refuse']}/{total}")

    # 输出对比表
    print("\n" + "=" * 60)
    print("  在线验证对比表")
    print("=" * 60)

    header = f"{'k':<5} {'平均Token':<12} {'输入Token':<12} {'直接回答':<10} {'联网兜底':<10} {'拒答':<8}"
    print(f"\n{header}")
    print("-" * len(header))

    for r in results:
        c = r["categories"]
        print(
            f"{r['k']:<5} "
            f"{r['avg_tokens_total']:<11.0f} "
            f"{r['avg_tokens_in']:<11.0f} "
            f"{c['direct']:<9} "
            f"{c['web_fallback']:<9} "
            f"{c['refuse']:<7}"
        )

    # 推荐: 平均 Token 最少且回答质量不低于阈值的最小 k
    # 筛选: 直接回答 >= 50% 的候选
    viable = [r for r in results if r["direct_ratio"] >= 0.5]
    if viable:
        best = min(viable, key=lambda x: x["avg_tokens_total"])
    else:
        best = min(results, key=lambda x: x["avg_tokens_total"])

    print(f"\n🏆 推荐 k={best['k']}")
    print(f"   平均 Token: {best['avg_tokens_total']:.0f} (输入 {best['avg_tokens_in']:.0f} / 输出 {best['avg_tokens_out']:.0f})")
    print(f"   直接回答: {best['categories']['direct']}/{len(ONLINE_SAMPLE)}")
    print(f"   联网兜底: {best['categories']['web_fallback']}/{len(ONLINE_SAMPLE)}")

    return results, best


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="retriever_k 调优")
    parser.add_argument("--phase", choices=["offline", "online", "all"], default="all")
    parser.add_argument("--k", nargs="+", type=int, default=[3, 5, 7],
                        help="Phase 2 候选 k 值")
    args = parser.parse_args()

    report = {"phase_offline": None, "phase_online": None}

    if args.phase in ("offline", "all"):
        offline_results, candidates = phase_offline()
        report["phase_offline"] = {
            "results": offline_results,
            "candidates": candidates,
        }
        # 用离线扫描的候选 k 值作为 Phase 2 的输入
        if args.phase == "all":
            args.k = candidates

    if args.phase in ("online", "all"):
        if not os.environ.get("DASHSCOPE_API_KEY"):
            from tests.conftest import _load_docker_env
            _load_docker_env()
        if not os.environ.get("DASHSCOPE_API_KEY"):
            print("\n⚠️  跳过 Phase 2: 需要 DASHSCOPE_API_KEY")
        else:
            online_results, best = phase_online(args.k)
            report["phase_online"] = {
                "results": online_results,
                "best_k": best["k"],
            }

    # 保存报告
    report_dir = Path(__file__).parent / "results"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "retriever_k_tuning_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📊 报告已保存: {report_path}")


if __name__ == "__main__":
    main()
