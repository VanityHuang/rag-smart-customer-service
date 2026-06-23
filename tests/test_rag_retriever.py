"""
离线评估 — 检索侧（Retriever）能力

评估对象：向量数据库的检索质量
评估方式：纯向量搜索，不调用 LLM
测试集：30 显式 + 20 隐式 + 20 噪声 = 70 题
指标：Hit Rate@3、MRR、平均最高相似度

用法（无需 API Key）:
    python -m pytest tests/test_rag_retriever.py -v -s
"""

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent / "data"

# ══════════════════════════════════════════════════════════════
# 测试集（与 test_rag_agent.py 共享）
# ══════════════════════════════════════════════════════════════

SEED_FILES = [
    "鸭鸭云服务器产品规格.md",
    "鸭鸭科技常见问题手册.txt",
    "鸭鸭科技员工手册.docx",
    "鸭鸭服务器运维手册.pdf",
    "鸭鸭科技业务报告.png",
]

# ── 30 个显式问题 ──
EXPLICIT_QUESTIONS = [
    {"question": "d1.small 实例的月费是多少", "expected": "99", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "d1.xlarge 有多少核CPU", "expected": "8 核", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "GPU型实例 g1.xlarge 配置了几个A10 GPU", "expected": "4×A10", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "SSD云盘的IOPS是多少", "expected": "20,000", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "超高IOPS盘的吞吐量是多少", "expected": "4,000 MB/s", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "对象存储中归档存储的单价是多少", "expected": "0.03", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "100Mbps公网带宽的月费是多少", "expected": "2000", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "负载均衡单实例最大并发连接数是多少", "expected": "500 万", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "DDoS高防最高防护能力是多少Gbps", "expected": "300 Gbps", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "旗舰版技术支持的响应时间是多少", "expected": "15 分钟", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "鸭鸭科技提供哪三大核心产品线", "expected": "鸭鸭 ERP、鸭鸭 CRM、鸭鸭 BI", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "SaaS云端部署的起步价是多少", "expected": "9800 元/年/10 用户", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "免费试用期是多少天", "expected": "14 天", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "技术支持热线电话是多少", "expected": "400-800-9966", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "数据存储在阿里云哪个区域", "expected": "华东2（上海）", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "数据加密传输层使用什么协议", "expected": "TLS 1.3", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "基础版API每天可以调用多少次", "expected": "1000 次/天", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "3年合同享受几折优惠", "expected": "8 折", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "忘记密码后重置链接有效期是多久", "expected": "30 分钟", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "账号注销冷静期是多少天", "expected": "7 天", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "内存型实例m1.large的内存是多少", "expected": "32 GB", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "专业版技术支持的服务时间是什么", "expected": "工作日 8-22", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "高效云盘的容量范围是多少", "expected": "20-32,768 GB", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "对象存储深度归档的年访问率要求是多少", "expected": "不到 1%", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "华南1深圳到北京的延迟是多少", "expected": "25ms", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "旗舰版API每天可以调用多少次", "expected": "100000 次/天", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "专业版套餐包含多少用户", "expected": "50 用户", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "预置集成了哪些即时通讯系统", "expected": "钉钉/企业微信/飞书", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "备份数据保留多少天", "expected": "90 天", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "数据加密存储层使用什么加密方式", "expected": "AES-256", "source": "鸭鸭科技常见问题手册.txt"},
]

# ── 20 个隐式问题 ──
IMPLICIT_QUESTIONS = [
    {"question": "搭建一个中小型网站每月最低需要多少钱", "expected": "199", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "如果我需要跑Redis缓存服务，应该选哪种实例", "expected": "m1.medium", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "我想做AI推理但预算有限，推荐哪种GPU实例", "expected": "g1.medium", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "ddos攻击防护免费版能防多少流量", "expected": "5 Gbps", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "我想试用产品但不想绑定信用卡可以吗", "expected": "14 天免费试用，无需绑定信用卡", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "公司的财务数据怎么和鸭鸭系统同步", "expected": "金蝶/用友", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "用户数据删除后还能恢复吗", "expected": "数据删除后不可恢复", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "员工忘记密码怎么处理", "expected": "登录页点击忘记密码", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "如果API调用超限了会怎样", "expected": "返回 HTTP 429 状态码，次日重置", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "5年合同比3年合同多优惠多少", "expected": "7 折 vs 8 折", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "香港服务器到大陆延迟大概多少", "expected": "35ms", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "高并发内存数据库应该选哪种规格", "expected": "d1.2xlarge", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "负载均衡支持哪些层级的协议", "expected": "四层（TCP/UDP）和七层（HTTP/HTTPS）", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "企业应用中等流量网站推荐什么配置", "expected": "d1.large", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "如何延长免费试用期", "expected": "联系销售可申请延长至 30 天", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "电子发票多久能收到", "expected": "付款后 3 个工作日内", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "外部协作者能看企业通讯录吗", "expected": "不可查看企业通讯录", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "专业版套餐包含哪些高级功能", "expected": "高级分析和自动化", "source": "鸭鸭科技常见问题手册.txt"},
    {"question": "哪些地方部署了鸭鸭云服务器节点", "expected": "华北1（北京）、华东2（上海）、华南1（深圳）、港澳台（香港）、东南亚（新加坡）、北美（硅谷）", "source": "鸭鸭云服务器产品规格.md"},
    {"question": "游戏服务器应该选哪种计算型实例", "expected": "c1.xlarge", "source": "鸭鸭云服务器产品规格.md"},
]

# ── 20 个域外噪声题 ──
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


# ══════════════════════════════════════════════════════════════
# 评估逻辑
# ══════════════════════════════════════════════════════════════

def _setup_knowledge_base():
    """上传测试文档到知识库"""
    from knowledge_base import KnowledgeBaseService

    kb = KnowledgeBaseService()
    for filename in SEED_FILES:
        fpath = DATA_DIR / filename
        if not fpath.exists():
            print(f"  ⚠️  跳过 {filename}（文件不存在）")
            continue
        file_bytes = fpath.read_bytes()
        result = kb.upload_by_file(file_bytes, filename)
        print(f"  📄 {filename}: {result}")


def _evaluate_retriever(questions: list, label: str) -> dict:
    """纯向量检索评估（不调 LLM）"""
    from vector_stores import VectorStoreService
    from langchain_community.embeddings import DashScopeEmbeddings
    import config_data as config

    vector_service = VectorStoreService(
        embedding=DashScopeEmbeddings(model=config.embedding_model_name),
        collection_name="rag_admin",
        persist_directory="./data/chroma_db/admin",
    )

    total = len(questions)
    hits = 0
    reciprocal_ranks = []
    similarities = []

    for i, q in enumerate(questions):
        question = q["question"]
        expected = q["expected"]

        results = vector_service.vector_store.similarity_search_with_score(question, k=3)

        if results:
            best_score = results[0][1]
            best_similarity = 1 - best_score
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
                reciprocal_ranks.append(1.0 / best_rank if best_rank else 0.0)
            else:
                reciprocal_ranks.append(0.0)

            status = "✅" if hit else "❌"
            print(f"  [{label}] ({i+1}/{total}) {question}")
            print(f"    sim={best_similarity:.4f} {status}")
        else:
            similarities.append(0.0)
            reciprocal_ranks.append(0.0)
            print(f"  [{label}] ({i+1}/{total}) {question}")
            print(f"    无结果 ❌")

    hit_rate = hits / total if total else 0.0
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0
    avg_sim = sum(similarities) / len(similarities) if similarities else 0.0

    return {
        "label": label,
        "total": total,
        "hits": hits,
        "hit_rate": hit_rate,
        "mrr": mrr,
        "avg_similarity": avg_sim,
    }


# ══════════════════════════════════════════════════════════════
# Pytest
# ══════════════════════════════════════════════════════════════

def test_rag_retriever():
    """离线评估：检索侧能力（无需 API Key）"""
    print("\n" + "=" * 60)
    print("  离线评估 — 检索侧（Retriever）")
    print("=" * 60)

    print("\n📥 上传测试文档到知识库...")
    _setup_knowledge_base()

    print("\n🔍 评估显式问题 (30 题)...")
    explicit = _evaluate_retriever(EXPLICIT_QUESTIONS, "显式")

    print("\n🔍 评估隐式问题 (20 题)...")
    implicit = _evaluate_retriever(IMPLICIT_QUESTIONS, "隐式")

    print("\n🔍 评估域外噪声题 (20 题)...")
    noise = _evaluate_retriever(NOISE_QUESTIONS, "噪声")

    # 输出报告
    print("\n" + "=" * 60)
    print("  离线评估报告")
    print("=" * 60)

    header = f"{'测试集':<10} {'数量':<6} {'命中':<6} {'Hit Rate@3':<12} {'MRR':<10} {'平均最高相似度':<14}"
    print(f"\n{header}")
    print("-" * len(header))

    for r in [explicit, implicit, noise]:
        print(
            f"{r['label']:<8} "
            f"{r['total']:<5} "
            f"{r['hits']:<5} "
            f"{r['hit_rate']:<11.0%} "
            f"{r['mrr']:<9.2%} "
            f"{r['avg_similarity']:<13.4f}"
        )

    # 写入报告
    report_dir = Path(__file__).parent.parent / "results"
    report_dir.mkdir(exist_ok=True)
    report = {
        "type": "offline_retriever",
        "config": {"score_high": 0.2, "score_low": 0.5, "retriever_k": 3},
        "results": [explicit, implicit, noise],
    }
    report_path = report_dir / "rag_retriever_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  📊 报告已保存: {report_path}")

    # 断言
    assert explicit["hit_rate"] >= 0.8, f"显式题 Hit Rate 低于 80%: {explicit['hit_rate']:.0%}"
