"""
chunk_size × overlap 参数遍历 — 离线评估

遍历 4×4 = 16 种组合，每种重建索引并跑 70 题离线评估，
输出对比表并推荐最佳参数组合。

用法（无需 API Key）:
    python tune_chunk_params.py

依赖:
    pip install -r requirements.txt（宿主机需安装依赖）
"""

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# ── 参数搜索范围 ──
CHUNK_SIZES = [128, 256, 512, 1024]
OVERLAPS = [0, 32, 64, 128]

# ── 复用测试集（与 test_rag_retriever.py 相同）──
sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "tests" / "data"

SEED_FILES = [
    "鸭鸭云服务器产品规格.md",
    "鸭鸭科技常见问题手册.txt",
    "鸭鸭科技员工手册.docx",
    "鸭鸭服务器运维手册.pdf",
    "鸭鸭科技业务报告.png",
]

# 显式 + 隐式 + 噪声 = 70 题（内联，避免 import 测试文件）
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


def _build_index(chunk_size: int, chunk_overlap: int, tmp_dir: str):
    """用指定参数重建 Chroma 索引"""
    from langchain_chroma import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    import hashlib

    embedding = DashScopeEmbeddings(model="text-embedding-v4")
    chroma = Chroma(
        collection_name="tune_test",
        embedding_function=embedding,
        persist_directory=tmp_dir,
        collection_metadata={"hnsw:space": "cosine"},
    )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""],
        length_function=len,
    )

    for filename in SEED_FILES:
        fpath = DATA_DIR / filename
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        if not text:
            # 二进制文件（PDF/DOCX/图片），用 file_parser 解析
            from file_parser import parse_bytes
            file_bytes = fpath.read_bytes()
            text = parse_bytes(file_bytes, filename)
        if not text:
            continue

        chunks = splitter.split_text(text) if len(text) > 1000 else [text]
        chroma.add_texts(
            chunks,
            metadatas=[{"source": filename}] * len(chunks),
        )

    return chroma


def _evaluate(chroma, questions: list) -> dict:
    """纯向量检索评估"""
    hits = 0
    reciprocal_ranks = []
    similarities = []

    for label, q in questions:
        question = q["question"]
        expected = q["expected"]

        results = chroma.similarity_search_with_score(question, k=3)
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

    total = len(questions)
    return {
        "hit_rate": hits / total if total else 0.0,
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0,
        "avg_similarity": sum(similarities) / len(similarities) if similarities else 0.0,
        "hits": hits,
        "total": total,
    }


def main():
    results = []
    total_combos = len(CHUNK_SIZES) * len(OVERLAPS)
    combo_idx = 0

    print("=" * 70)
    print("  chunk_size × overlap 参数遍历")
    print(f"  搜索范围: chunk_size={CHUNK_SIZES}, overlap={OVERLAPS}")
    print(f"  共 {total_combos} 种组合 × 70 题 = {total_combos * 70} 次检索")
    print("=" * 70)

    for cs in CHUNK_SIZES:
        for co in OVERLAPS:
            combo_idx += 1
            # overlap 不能 >= chunk_size
            if co >= cs:
                print(f"\n[{combo_idx}/{total_combos}] chunk_size={cs}, overlap={co} → 跳过 (overlap >= chunk_size)")
                continue

            print(f"\n[{combo_idx}/{total_combos}] chunk_size={cs}, overlap={co}")

            with tempfile.TemporaryDirectory() as tmp_dir:
                start = time.time()
                chroma = _build_index(cs, co, tmp_dir)
                build_time = time.time() - start

                # 统计 chunk 数量
                chunk_count = len(chroma.get()["ids"])

                start = time.time()
                eval_result = _evaluate(chroma, ALL_QUESTIONS)
                eval_time = time.time() - start

                # 按类别拆分
                explicit_q = [q for q in ALL_QUESTIONS if q[0] == "显式"]
                implicit_q = [q for q in ALL_QUESTIONS if q[0] == "隐式"]
                noise_q = [q for q in ALL_QUESTIONS if q[0] == "噪声"]

                explicit_eval = _evaluate(chroma, explicit_q)
                implicit_eval = _evaluate(chroma, implicit_q)
                noise_eval = _evaluate(chroma, noise_q)

                row = {
                    "chunk_size": cs,
                    "overlap": co,
                    "chunk_count": chunk_count,
                    "build_time": f"{build_time:.1f}s",
                    "overall_hit_rate": eval_result["hit_rate"],
                    "overall_mrr": eval_result["mrr"],
                    "overall_similarity": eval_result["avg_similarity"],
                    "explicit_hit_rate": explicit_eval["hit_rate"],
                    "explicit_mrr": explicit_eval["mrr"],
                    "implicit_hit_rate": implicit_eval["hit_rate"],
                    "implicit_mrr": implicit_eval["mrr"],
                    "noise_hit_rate": noise_eval["hit_rate"],
                    "noise_similarity": noise_eval["avg_similarity"],
                }
                results.append(row)

                print(f"  chunks={chunk_count} | "
                      f"显式={explicit_eval['hit_rate']:.0%} | "
                      f"隐式={implicit_eval['hit_rate']:.0%} | "
                      f"噪声={noise_eval['hit_rate']:.0%} | "
                      f"相似度={eval_result['avg_similarity']:.4f}")

    # ── 输出对比表 ──
    print("\n" + "=" * 70)
    print("  参数对比表")
    print("=" * 70)

    header = f"{'chunk_size':<11} {'overlap':<9} {'chunks':<8} {'显式HR':<8} {'隐式HR':<8} {'噪声HR':<8} {'MRR':<8} {'相似度':<8}"
    print(f"\n{header}")
    print("-" * len(header))

    for r in results:
        print(
            f"{r['chunk_size']:<10} "
            f"{r['overlap']:<8} "
            f"{r['chunk_count']:<7} "
            f"{r['explicit_hit_rate']:<7.0%} "
            f"{r['implicit_hit_rate']:<7.0%} "
            f"{r['noise_hit_rate']:<7.0%} "
            f"{r['overall_mrr']:<7.2%} "
            f"{r['overall_similarity']:<7.4f}"
        )

    # ── 推荐最佳参数 ──
    # 评分公式: 显式HR×0.4 + 隐式HR×0.3 + (1-噪声HR)×0.2 + MRR×0.1
    for r in results:
        r["score"] = (
            r["explicit_hit_rate"] * 0.4
            + r["implicit_hit_rate"] * 0.3
            + (1 - r["noise_hit_rate"]) * 0.2
            + r["overall_mrr"] * 0.1
        )

    best = max(results, key=lambda x: x["score"])
    print(f"\n{'=' * 70}")
    print(f"  🏆 推荐最佳参数: chunk_size={best['chunk_size']}, overlap={best['overlap']}")
    print(f"     显式 Hit Rate: {best['explicit_hit_rate']:.0%}")
    print(f"     隐式 Hit Rate: {best['implicit_hit_rate']:.0%}")
    print(f"     噪声 Hit Rate: {best['noise_hit_rate']:.0%}")
    print(f"     MRR: {best['overall_mrr']:.2%}")
    print(f"     平均相似度: {best['overall_similarity']:.4f}")
    print(f"     综合评分: {best['score']:.4f}")
    print(f"{'=' * 70}")

    # ── 保存报告 ──
    report_dir = Path(__file__).parent / "results"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "chunk_tuning_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "search_space": {"chunk_sizes": CHUNK_SIZES, "overlaps": OVERLAPS},
            "results": results,
            "best": best,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📊 报告已保存: {report_path}")


if __name__ == "__main__":
    main()
