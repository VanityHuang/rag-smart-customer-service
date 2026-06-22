"""
RAG 参数遍历 — chunk_size × overlap 网格搜索

暴力遍历 9 种参数组合，每种组合上传测试文档并计算 Hit Rate + MRR，
最终输出对比表。用户自行运行并分析结果。

用法:
    python -m pytest tests/test_rag_precision_grid.py -v -s

产出:
    - 终端输出 Markdown 对比表
    - results/rag_precision_grid.csv

前置条件:
    - DASHSCOPE_API_KEY 环境变量
    - 本地 Chroma 可写（使用临时目录，不污染正式数据）
"""

import csv
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Tuple

import pytest

# 确保能导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 测试参数组合 ──
PARAM_GRID = [
    {"chunk_size": 256, "chunk_overlap": 0},
    {"chunk_size": 256, "chunk_overlap": 64},
    {"chunk_size": 256, "chunk_overlap": 128},
    {"chunk_size": 512, "chunk_overlap": 0},
    {"chunk_size": 512, "chunk_overlap": 64},
    {"chunk_size": 512, "chunk_overlap": 128},
    {"chunk_size": 1024, "chunk_overlap": 0},
    {"chunk_size": 1024, "chunk_overlap": 64},
    {"chunk_size": 1024, "chunk_overlap": 128},
]

# ── 测试文档（与 evaluation.py 一致） ──
TEST_DOCUMENTS: List[Tuple[str, str]] = [
    (
        "毛衣保养：针织毛衣建议手洗，使用羊毛专用洗涤剂，水温不超过30度。"
        "洗涤后轻压挤水，平铺晾干避免悬挂变形。针织护理要点包括定期除毛球、防虫蛀。",
        "clothing_care.txt",
    ),
    (
        "羽绒服清洗：羽绒服建议干洗或手洗，不可机洗甩干。"
        "洗后阴干不可暴晒，晾干后轻轻拍打恢复蓬松。存放时避免重压。",
        "down_jacket.txt",
    ),
    (
        "牛仔护理：牛仔裤建议减少水洗频率，翻面冷水洗涤，避免烘干。"
        "长时间不穿可密封袋保存，防止受潮变色。",
        "jeans.txt",
    ),
    (
        "实木家具保养：避免阳光直射，定期打蜡抛光。"
        "用软布除尘，远离暖气片和空调出风口，避免温差过大导致开裂。",
        "wood_furniture.txt",
    ),
    (
        "皮质沙发护理：真皮沙发定期用专用皮革护理剂擦拭保养，"
        "每隔半年做一次深度护理。避免尖锐物品划伤表面。",
        "leather_sofa.txt",
    ),
    (
        "地板养护：木地板避免大量水拖，使用专用清洁剂。"
        "保持室内湿度在40%-60%之间，避免热源长时间直射。",
        "flooring.txt",
    ),
    (
        "手机电池保养：锂电池随用随充，避免彻底放空。"
        "每月做一次完整充放电循环以校准电量，长期存放保持50%电量。",
        "phone_battery.txt",
    ),
    (
        "电脑散热维护：定期清理散热口和风扇灰尘，使用散热支架。"
        "避免在床上或软面使用，堵塞进风口会导致性能下降。",
        "pc_cooling.txt",
    ),
    (
        "相机防潮保存：相机和镜头应置于防潮箱，湿度控制在40%-50%。"
        "长期不用时电池取出单独存放，镜头定期除霉检查。",
        "camera.txt",
    ),
]

# 干扰文档
DISTRACTOR_DOCUMENTS: List[Tuple[str, str]] = [
    (
        "丝巾保养：真丝丝巾建议干洗或手洗，使用中性洗涤剂。"
        "不可用力拧干，低温熨烫时垫布保护。",
        "distract_scarf.txt",
    ),
    (
        "鞋子收纳：换季鞋子清洁干燥后放入收纳箱，内塞鞋楦防变形。"
        "真皮鞋子定期上油保养，避免受潮发霉。",
        "distract_shoes.txt",
    ),
    (
        "不锈钢家具清洁：不锈钢表面用软布蘸中性清洁剂擦拭，"
        "避免使用钢丝球或含氯清洁剂，防止表面氧化。",
        "distract_stainless.txt",
    ),
    (
        "窗帘清洗保养：不同材质窗帘清洗方式不同，"
        "布艺窗帘可机洗，绒面建议干洗，百叶窗帘用湿布擦拭即可。",
        "distract_curtains.txt",
    ),
    (
        "平板电脑贴膜：选择AR增透膜减少反光，"
        "贴膜前清除灰尘，边缘对齐后缓慢放下，气泡用刮卡推出。",
        "distract_tablet.txt",
    ),
    (
        "机械键盘清洁：用拔键器拆下键帽，键帽浸泡清洗。"
        "键盘主体用毛刷清理灰尘，不宜使用酒精以免损伤电路。",
        "distract_keyboard.txt",
    ),
]

# 测试用例: (查询, 相关关键词, 难度)
TEST_CASES: List[Tuple[str, List[str], str]] = [
    ("毛衣怎么保养",               ["毛衣保养", "针织护理"], "easy"),
    ("实木家具保养方法有哪些",     ["实木家具保养"],         "easy"),
    ("手机电池怎样充电正确",       ["手机电池保养", "锂电池"], "easy"),
    ("羊毛衫洗护注意事项",         ["毛衣保养", "针织护理"], "medium"),
    ("真皮沙发怎么护理",           ["皮质沙发护理"],         "medium"),
    ("笔记本散热不好怎么办",       ["电脑散热维护"],         "medium"),
    ("冬天的厚外套怎么清洗",       ["羽绒服清洗", "毛衣保养"], "hard"),
    ("夏天相机不用了怎么存放",     ["相机防潮保存"],         "hard"),
    ("新家地板和家具怎么打理",     ["实木家具保养", "地板养护"], "hard"),
]

# 域外问题（不应命中任何文档）
OUT_OF_DOMAIN_QUERIES = [
    "今天天气怎么样",
    "食堂今天吃什么",
    "最近有什么电影",
    "股票行情如何",
    "怎么做红烧肉",
]


@pytest.mark.external
def test_parameter_grid():
    """遍历 chunk_size × overlap 参数组合，输出对比表"""
    from langchain_community.embeddings import DashScopeEmbeddings

    import config_data as config
    from knowledge_base import KnowledgeBaseService, get_string_md5, check_md5
    from vector_stores import VectorStoreService

    embedding = DashScopeEmbeddings(model=config.embedding_model_name)
    results = []

    for params in PARAM_GRID:
        cs = params["chunk_size"]
        co = params["chunk_overlap"]

        # 用临时目录做隔离的 Chroma 库
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建临时 vector store
            vs = VectorStoreService(
                embedding=embedding,
                persist_directory=tmpdir,
            )
            kb = KnowledgeBaseService(vector_service=vs)

            # 上传测试文档 + 干扰文档
            for text, filename in TEST_DOCUMENTS + DISTRACTOR_DOCUMENTS:
                md5 = get_string_md5(text)
                if not check_md5(md5, md5_file=os.path.join(tmpdir, "md5.text")):
                    kb.upload_by_str(
                        text, filename,
                        chunk_size=cs, chunk_overlap=co,
                    )

            retriever = vs.get_retriever(k=3)

            # 域内 Hit Rate + MRR
            hits = 0
            reciprocal_ranks = []
            for query, relevant, _ in TEST_CASES:
                docs = retriever.invoke(query)
                texts = [d.page_content for d in docs]

                is_hit = any(
                    rel in doc for doc in texts for rel in relevant
                )
                if is_hit:
                    hits += 1

                best_rank = None
                for rank, doc in enumerate(docs, start=1):
                    if any(rel in doc.page_content for rel in relevant):
                        best_rank = rank
                        break
                rr = 1.0 / best_rank if best_rank else 0.0
                reciprocal_ranks.append(rr)

            n = len(TEST_CASES)
            hit_rate = hits / n if n else 0.0
            mrr = statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0.0

            # 域外误召回率
            ood_hits = 0
            for query in OUT_OF_DOMAIN_QUERIES:
                docs = retriever.invoke(query)
                texts = [d.page_content for d in docs]
                # 检查是否命中了干扰文档（不应命中）
                if any(
                    any(distract_text[:10] in t for t in texts)
                    for distract_text, _ in DISTRACTOR_DOCUMENTS
                ):
                    ood_hits += 1
            ood_recall_rate = ood_hits / len(OUT_OF_DOMAIN_QUERIES)

            results.append({
                "chunk_size": cs,
                "chunk_overlap": co,
                "hit_rate": hit_rate,
                "mrr": mrr,
                "ood_recall": ood_recall_rate,
            })

            print(
                f"  chunk_size={cs:>4}, overlap={co:>3} → "
                f"Hit Rate={hit_rate:.0%}, MRR={mrr:.2%}, OOD Recall={ood_recall_rate:.0%}"
            )

    # 输出 Markdown 对比表
    print("\n" + "=" * 70)
    print("RAG 参数遍历结果")
    print("=" * 70)
    print(f"\n| chunk_size | overlap | Hit Rate | MRR    | OOD Recall |")
    print(f"|------------|---------|----------|--------|------------|")
    for r in results:
        print(
            f"| {r['chunk_size']:>10} | {r['chunk_overlap']:>7} | "
            f"{r['hit_rate']:>8.0%} | {r['mrr']:.2%} | {r['ood_recall']:>10.0%} |"
        )

    # 找最优组合（Hit Rate 最高，MRR 最高）
    best = max(results, key=lambda x: (x["hit_rate"], x["mrr"]))
    print(f"\n最优参数: chunk_size={best['chunk_size']}, overlap={best['chunk_overlap']}")
    print(f"  Hit Rate: {best['hit_rate']:.0%}")
    print(f"  MRR:      {best['mrr']:.2%}")
    print(f"  OOD Recall: {best['ood_recall']:.0%}")

    # 写入 CSV
    csv_dir = Path(__file__).parent.parent / "results"
    csv_dir.mkdir(exist_ok=True)
    csv_path = csv_dir / "rag_precision_grid.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["chunk_size", "chunk_overlap", "hit_rate", "mrr", "ood_recall"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n结果已保存: {csv_path}")

    # 断言最优组合的 Hit Rate >= 80%
    assert best["hit_rate"] >= 0.8, f"最优组合 Hit Rate 低于 80%: {best['hit_rate']:.0%}"
