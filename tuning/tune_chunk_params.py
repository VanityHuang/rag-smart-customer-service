"""
chunk_size × overlap 参数遍历 — 离线评估

遍历多种参数组合，每种重建索引并跑 70 题离线评估，
输出对比表并推荐最佳参数组合。

用法（无需 API Key）:
    python tuning/tune_chunk_params.py                        # 默认 16 种组合
    python tuning/tune_chunk_params.py --fast                 # 快速模式（6 种组合）
    python tuning/tune_chunk_params.py --sizes 256 512 --overlaps 32 64  # 自定义范围
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _load_docker_env():
    """从 docker/.env 加载环境变量"""
    env_path = Path(__file__).parent.parent / "docker" / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value


_load_docker_env()

DATA_DIR = Path(__file__).parent.parent / "tests" / "data"

SEED_FILES = [
    "鸭鸭云服务器产品规格.md",
    "鸭鸭科技常见问题手册.txt",
    "鸭鸭科技员工手册.docx",
    "鸭鸭服务器运维手册.pdf",
    "鸭鸭科技业务报告.png",
]

# ── 验证测试集（覆盖全部 5 个文档）──
# 来源: 产品规格.md + FAQ.txt + 员工手册.docx + 运维手册.pdf + 业务报告.png

EXPLICIT_QUESTIONS = [
    # ── 产品规格.md ──
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
    {"question": "内存型实例m1.large的内存是多少", "expected": "32 GB"},
    {"question": "高效云盘的容量范围是多少", "expected": "20-32,768 GB"},
    {"question": "对象存储深度归档的年访问率要求", "expected": "不到 1%"},
    # ── FAQ.txt ──
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
    {"question": "专业版套餐包含多少用户", "expected": "50 用户"},
    {"question": "备份数据保留多少天", "expected": "90 天"},
    {"question": "数据加密存储层使用什么加密方式", "expected": "AES-256"},
    # ── 运维手册.pdf ──
    {"question": "鸭鸭云服务器推荐什么操作系统", "expected": "CentOS 7.9 或 Ubuntu 22.04 LTS"},
    {"question": "系统盘推荐多大容量", "expected": "SSD 云盘 50GB"},
    {"question": "数据盘最低不少于多少", "expected": "不低于 100GB"},
    {"question": "实例创建后多久可使用", "expected": "3-5 分钟"},
    {"question": "创建运维账号的命令是什么", "expected": "useradd -m -s /bin/bash ops"},
    # ── 业务报告.png ──
    {"question": "鸭鸭科技2024年营业收入", "expected": "2.36 亿元"},
    {"question": "鸭鸭科技2024年净利润", "expected": "3460万元"},
    {"question": "鸭鸭科技2024年研发投入", "expected": "1870万元"},
    {"question": "鸭鸭科技服务多少客户", "expected": "1200+"},
    {"question": "鸭鸭科技2024年营收同比增长", "expected": "32.6%"},
]

IMPLICIT_QUESTIONS = [
    # ── 需要跨文档推理 ──
    {"question": "搭建中小型网站每月最低费用", "expected": "199"},
    {"question": "跑Redis缓存服务选哪种实例", "expected": "m1.medium"},
    {"question": "预算有限做AI推理推荐哪种GPU", "expected": "g1.medium"},
    {"question": "DDoS免费防护能防多少流量", "expected": "5 Gbps"},
    {"question": "不想绑定信用卡能试用吗", "expected": "无需绑定信用卡"},
    {"question": "数据删除后能恢复吗", "expected": "数据删除后不可恢复"},
    {"question": "API调用超限会怎样", "expected": "429"},
    {"question": "5年合同比3年优惠多少", "expected": "7 折"},
    {"question": "高并发内存数据库选哪种规格", "expected": "d1.2xlarge"},
    {"question": "负载均衡支持哪些协议层级", "expected": "四层（TCP/UDP）和七层（HTTP/HTTPS）"},
    {"question": "中等流量企业网站推荐什么配置", "expected": "d1.large"},
    {"question": "电子发票多久能收到", "expected": "3 个工作日内"},
    {"question": "专业版套餐有哪些高级功能", "expected": "高级分析和自动化"},
    {"question": "游戏服务器选哪种计算型实例", "expected": "c1.xlarge"},
    {"question": "如何延长免费试用期", "expected": "延长至 30 天"},
    # ── 运维手册.pdf（隐式/操作相关）──
    {"question": "云服务器选择什么操作系统好", "expected": "CentOS 7.9"},
    {"question": "首次登录需要做什么", "expected": "修改默认密码"},
    {"question": "CentOS怎么更新系统", "expected": "yum update -y"},
    {"question": "Ubuntu怎么更新系统", "expected": "apt update && apt upgrade -y"},
    {"question": "配置时区的命令是什么", "expected": "timedatectl set-timezone Asia/Shanghai"},
    # ── 业务报告.png（隐式/数字推理）──
    {"question": "鸭鸭科技净利润增长率", "expected": "28.4%"},
    {"question": "客户数量增长率", "expected": "41.2%"},
    {"question": "研发投入增长率", "expected": "35.7%"},
    {"question": "鸭鸭科技有哪些核心业务", "expected": "云计算服务"},
    {"question": "鸭鸭科技成立时间", "expected": "2018 年"},
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


# ── ROUGE-L 文本重叠率 ──
def _lcs_length(x: str, y: str) -> int:
    """最长公共子序列长度（动态规划）"""
    m, n = len(x), len(y)
    if m == 0 or n == 0:
        return 0
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if x[i - 1] == y[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def rouge_l_precision(expected: str, content: str) -> float:
    """ROUGE-L Precision — expected 中有多少字符按序出现在 content 中"""
    if not expected or not content:
        return 0.0
    lcs = _lcs_length(expected, content)
    return lcs / len(expected) if len(expected) > 0 else 0.0


ROUGE_L_THRESHOLD = 0.8  # Precision >= 0.8 视为命中（expected 的 80%+ 字符在 chunk 中）


# ══════════════════════════════════════════════════════════════
# 核心逻辑
# ══════════════════════════════════════════════════════════════

def _preload_documents(max_chars: int = 100_000) -> dict:
    """预加载文档文本，跳过超大文件（避免嵌入 API 耗时过长）"""
    from file_parser import parse_bytes

    docs = {}
    skipped = []
    TEXT_EXT = {".txt", ".md"}
    for filename in SEED_FILES:
        fpath = DATA_DIR / filename
        if not fpath.exists():
            print(f"  ⚠️  {filename} 不存在，跳过")
            continue
        ext = fpath.suffix.lower()
        if ext in TEXT_EXT:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        else:
            # PDF/DOCX/PNG 等二进制文件，用 parse_bytes 解析
            file_bytes = fpath.read_bytes()
            text = parse_bytes(file_bytes, filename)
        if text:
            if len(text) > max_chars:
                skipped.append((filename, len(text)))
            else:
                docs[filename] = text
                print(f"  📄 {filename}: {len(text)} 字符")
    if skipped:
        print(f"  ⏭️  跳过 {len(skipped)} 个大文件（>{max_chars:,} 字符）:")
        for name, size in skipped:
            print(f"     {name}: {size:,} 字符")
    return docs


def _build_and_evaluate(docs: dict, chunk_size: int, chunk_overlap: int) -> dict:
    """用指定参数建索引 + 评估"""
    from langchain_chroma import Chroma
    from langchain_community.embeddings import DashScopeEmbeddings
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    import config_data as config

    embedding = config.get_embedding_model()

    with tempfile.TemporaryDirectory() as tmp_dir:
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

        total_chunks = 0
        for filename, text in docs.items():
            chunks = splitter.split_text(text) if len(text) > 1000 else [text]
            BATCH_SIZE = 5000
            for batch_start in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[batch_start:batch_start + BATCH_SIZE]
                chroma.add_texts(batch, metadatas=[{"source": filename}] * len(batch))
            total_chunks += len(chunks)

        # 评估
        hits = 0
        reciprocal_ranks = []
        similarities = []

        for label, q in ALL_QUESTIONS:
            results = chroma.similarity_search_with_score(q["question"], k=3)
            if results:
                similarities.append(1 - results[0][1])
                hit = False
                best_rank = None
                for rank, (doc, score) in enumerate(results, start=1):
                    expected = q["expected"]
                    content = doc.page_content
                    if expected and rouge_l_precision(expected, content) >= ROUGE_L_THRESHOLD:
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

        # 按类别拆分
        def _calc(subset):
            sub_hits = 0
            sub_rr = []
            sub_sim = []
            for label, q in subset:
                results = chroma.similarity_search_with_score(q["question"], k=3)
                if results:
                    sub_sim.append(1 - results[0][1])
                    hit = False
                    best_rank = None
                    for rank, (doc, score) in enumerate(results, start=1):
                        if q["expected"] and rouge_l_precision(q["expected"], doc.page_content) >= ROUGE_L_THRESHOLD:
                            hit = True
                            if best_rank is None:
                                best_rank = rank
                    if hit:
                        sub_hits += 1
                        sub_rr.append(1.0 / best_rank)
                    else:
                        sub_rr.append(0.0)
                else:
                    sub_sim.append(0.0)
                    sub_rr.append(0.0)
            n = len(subset)
            return {
                "hit_rate": sub_hits / n if n else 0,
                "mrr": sum(sub_rr) / len(sub_rr) if sub_rr else 0,
                "avg_similarity": sum(sub_sim) / len(sub_sim) if sub_sim else 0,
            }

        explicit_q = [q for q in ALL_QUESTIONS if q[0] == "显式"]
        implicit_q = [q for q in ALL_QUESTIONS if q[0] == "隐式"]
        noise_q = [q for q in ALL_QUESTIONS if q[0] == "噪声"]

        return {
            "chunk_size": chunk_size,
            "overlap": chunk_overlap,
            "chunk_count": total_chunks,
            "overall_hit_rate": hits / total,
            "overall_mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
            "overall_similarity": sum(similarities) / len(similarities),
            "explicit": _calc(explicit_q),
            "implicit": _calc(implicit_q),
            "noise": _calc(noise_q),
        }


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="chunk_size × overlap 参数遍历")
    parser.add_argument("--sizes", nargs="+", type=int, default=[128, 256, 512])
    parser.add_argument("--overlaps", nargs="+", type=int, default=[0, 32, 64, 128])
    parser.add_argument("--fast", action="store_true", help="快速模式: 256/512 × 32/64")
    parser.add_argument("--max-chars", type=int, default=5_000_000,
                        help="跳过超过此字符数的文档（默认 5000000，覆盖 5 个测试文档）")
    args = parser.parse_args()

    if args.fast:
        args.sizes = [256, 512]
        args.overlaps = [32, 64]

    # 生成有效组合（排除 overlap >= chunk_size）
    combos = [(cs, co) for cs in args.sizes for co in args.overlaps if co < cs]

    print("=" * 70)
    print("  chunk_size × overlap 参数遍历")
    print(f"  搜索范围: chunk_size={args.sizes}, overlap={args.overlaps}")
    print(f"  有效组合: {len(combos)} 种 × 70 题")
    print("=" * 70)

    # 预加载文档
    print("\n📥 预加载文档...")
    docs = _preload_documents(max_chars=args.max_chars)
    print(f"   共加载 {len(docs)} 个文档")

    # 遍历组合
    results = []
    for idx, (cs, co) in enumerate(combos, 1):
        print(f"\n[{idx}/{len(combos)}] chunk_size={cs}, overlap={co} ...", end=" ", flush=True)
        start = time.time()
        result = _build_and_evaluate(docs, cs, co)
        elapsed = time.time() - start
        result["time"] = f"{elapsed:.1f}s"
        results.append(result)
        print(
            f"chunks={result['chunk_count']} | "
            f"显式={result['explicit']['hit_rate']:.0%} | "
            f"隐式={result['implicit']['hit_rate']:.0%} | "
            f"噪声={result['noise']['hit_rate']:.0%} | "
            f"MRR={result['overall_mrr']:.2%} | "
            f"({elapsed:.1f}s)"
        )

    # 输出对比表
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
            f"{r['explicit']['hit_rate']:<7.0%} "
            f"{r['implicit']['hit_rate']:<7.0%} "
            f"{r['noise']['hit_rate']:<7.0%} "
            f"{r['overall_mrr']:<7.2%} "
            f"{r['overall_similarity']:<7.4f}"
        )

    # 推荐最佳参数
    for r in results:
        r["score"] = (
            r["explicit"]["hit_rate"] * 0.4
            + r["implicit"]["hit_rate"] * 0.3
            + (1 - r["noise"]["hit_rate"]) * 0.2
            + r["overall_mrr"] * 0.1
        )

    best = max(results, key=lambda x: x["score"])
    print(f"\n{'=' * 70}")
    print(f"  🏆 推荐最佳参数: chunk_size={best['chunk_size']}, overlap={best['overlap']}")
    print(f"     显式 Hit Rate: {best['explicit']['hit_rate']:.0%}")
    print(f"     隐式 Hit Rate: {best['implicit']['hit_rate']:.0%}")
    print(f"     噪声 Hit Rate: {best['noise']['hit_rate']:.0%}")
    print(f"     MRR: {best['overall_mrr']:.2%}")
    print(f"     平均相似度: {best['overall_similarity']:.4f}")
    print(f"     综合评分: {best['score']:.4f}")
    print(f"{'=' * 70}")

    # 保存报告
    report_dir = Path(__file__).parent / "results"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "chunk_tuning_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "search_space": {"chunk_sizes": args.sizes, "overlaps": args.overlaps},
            "results": results,
            "best": {"chunk_size": best["chunk_size"], "overlap": best["overlap"], "score": best["score"]},
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📊 报告已保存: {report_path}")


if __name__ == "__main__":
    main()
