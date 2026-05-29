"""
RAG 评估体系
量化指标: Hit Rate, MRR, 检索延迟

用法:
    python evaluation.py

自动播种测试文档、运行评估、清理数据，不影响已有知识库。
"""
import sys
import time
import statistics
import warnings
from typing import List, Tuple

# 确保终端输出 UTF-8（解决 Windows GBK 乱码）
if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

import config_data as config
from vector_stores import VectorStoreService
from knowledge_base import KnowledgeBaseService, get_string_md5, check_md5

warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community")
from langchain_community.embeddings import DashScopeEmbeddings

# ── 内嵌测试数据集 ──────────────────────────────────
# 每个元组: (文档内容, 文件名, 类别)
_TEST_DOCUMENTS: List[Tuple[str, str, str]] = [
    # 服装保养
    (
        "毛衣保养：针织毛衣建议手洗，使用羊毛专用洗涤剂，水温不超过30度。"
        "洗涤后轻压挤水，平铺晾干避免悬挂变形。针织护理要点包括定期除毛球、防虫蛀。",
        "test_clothing_care.txt", "服装",
    ),
    (
        "羽绒服清洗：羽绒服建议干洗或手洗，不可机洗甩干。"
        "洗后阴干不可暴晒，晾干后轻轻拍打恢复蓬松。存放时避免重压。",
        "test_down_jacket.txt", "服装",
    ),
    (
        "牛仔护理：牛仔裤建议减少水洗频率，翻面冷水洗涤，避免烘干。"
        "长时间不穿可密封袋保存，防止受潮变色。",
        "test_jeans.txt", "服装",
    ),
    # 家居养护
    (
        "实木家具保养：避免阳光直射，定期打蜡抛光。"
        "用软布除尘，远离暖气片和空调出风口，避免温差过大导致开裂。",
        "test_wood_furniture.txt", "家居",
    ),
    (
        "皮质沙发护理：真皮沙发定期用专用皮革护理剂擦拭保养，"
        "每隔半年做一次深度护理。避免尖锐物品划伤表面。",
        "test_leather_sofa.txt", "家居",
    ),
    (
        "地板养护：木地板避免大量水拖，使用专用清洁剂。"
        "保持室内湿度在40%-60%之间，避免热源长时间直射。",
        "test_flooring.txt", "家居",
    ),
    # 数码设备
    (
        "手机电池保养：锂电池随用随充，避免彻底放空。"
        "每月做一次完整充放电循环以校准电量，长期存放保持50%电量。",
        "test_phone_battery.txt", "数码",
    ),
    (
        "电脑散热维护：定期清理散热口和风扇灰尘，使用散热支架。"
        "避免在床上或软面使用，堵塞进风口会导致性能下降。",
        "test_pc_cooling.txt", "数码",
    ),
    (
        "相机防潮保存：相机和镜头应置于防潮箱，湿度控制在40%-50%。"
        "长期不用时电池取出单独存放，镜头定期除霉检查。",
        "test_camera.txt", "数码",
    ),
]

# 干扰文档：主题相关但不匹配任何查询，增加检索难度
_DISTRACTOR_DOCUMENTS: List[Tuple[str, str, str]] = [
    # 服装类干扰
    (
        "丝巾保养：真丝丝巾建议干洗或手洗，使用中性洗涤剂。"
        "不可用力拧干，低温熨烫时垫布保护。",
        "distract_scarf.txt", "服装",
    ),
    (
        "鞋子收纳：换季鞋子清洁干燥后放入收纳箱，内塞鞋楦防变形。"
        "真皮鞋子定期上油保养，避免受潮发霉。",
        "distract_shoes.txt", "服装",
    ),
    # 家居类干扰
    (
        "不锈钢家具清洁：不锈钢表面用软布蘸中性清洁剂擦拭，"
        "避免使用钢丝球或含氯清洁剂，防止表面氧化。",
        "distract_stainless.txt", "家居",
    ),
    (
        "窗帘清洗保养：不同材质窗帘清洗方式不同，"
        "布艺窗帘可机洗，绒面建议干洗，百叶窗帘用湿布擦拭即可。",
        "distract_curtains.txt", "家居",
    ),
    # 数码类干扰
    (
        "平板电脑贴膜：选择AR增透膜减少反光，"
        "贴膜前清除灰尘，边缘对齐后缓慢放下，气泡用刮卡推出。",
        "distract_tablet.txt", "数码",
    ),
    (
        "机械键盘清洁：用拔键器拆下键帽，键帽浸泡清洗。"
        "键盘主体用毛刷清理灰尘，不宜使用酒精以免损伤电路。",
        "distract_keyboard.txt", "数码",
    ),
]

# 测试用例: (查询, 相关关键词, 难度)
#   easy   — 文档直接包含查询关键词
#   medium — 语义匹配，用词不同但意思相同
#   hard   — 涉及多文档或需要推理，无直接关键词匹配
_TEST_CASES: List[Tuple[str, List[str], str]] = [
    # easy
    ("毛衣怎么保养",               ["毛衣保养", "针织护理"], "easy"),
    ("实木家具保养方法有哪些",     ["实木家具保养"],         "easy"),
    ("手机电池怎样充电正确",       ["手机电池保养", "锂电池"],"easy"),
    # medium
    ("羊毛衫洗护注意事项",         ["毛衣保养", "针织护理"], "medium"),
    ("真皮沙发怎么护理",           ["皮质沙发护理"],         "medium"),
    ("笔记本散热不好怎么办",       ["电脑散热维护"],         "medium"),
    # hard
    ("冬天的厚外套怎么清洗",       ["羽绒服清洗", "毛衣保养"],"hard"),
    ("夏天相机不用了怎么存放",     ["相机防潮保存"],         "hard"),
    ("新家地板和家具怎么打理",     ["实木家具保养", "地板养护"],"hard"),
]


class RagEvaluator:
    def __init__(self, auto_seed: bool = True):
        self.vector_service = VectorStoreService(
            embedding=DashScopeEmbeddings(model=config.embedding_model_name)
        )
        self._seeded_sources: List[str] = []
        if auto_seed:
            self._seeded_sources = self._seed_test_data()

    def _seed_test_data(self) -> List[str]:
        kb = KnowledgeBaseService()
        sources = []
        for text, filename, _ in _TEST_DOCUMENTS + _DISTRACTOR_DOCUMENTS:
            md5 = get_string_md5(text)
            if not check_md5(md5):
                kb.upload_by_str(text, filename)
            sources.append(filename)
        return sources

    def cleanup_test_data(self):
        if not self._seeded_sources:
            return
        kb = KnowledgeBaseService()
        for src in self._seeded_sources:
            kb.delete_document(src)
        self._seeded_sources = []

    def evaluate(self, k: int = None) -> dict:
        """执行全量评估，返回逐条明细和汇总指标"""
        k = k or config.retriever_k
        retriever = self.vector_service.get_retriever(k=k)

        details = []
        hits = 0
        reciprocal_ranks = []

        for query, relevant, difficulty in _TEST_CASES:
            retrieved = retriever.invoke(query)
            retrieved_texts = [doc.page_content for doc in retrieved]

            # Hit: 至少一个相关关键词出现在检索结果中
            is_hit = any(
                rel in doc for doc in retrieved_texts for rel in relevant
            )
            if is_hit:
                hits += 1

            # MRR: 第一个相关文档的排名
            best_rank = None
            for rank, doc in enumerate(retrieved, start=1):
                if any(rel in doc.page_content for rel in relevant):
                    best_rank = rank
                    break
            rr = 1.0 / best_rank if best_rank else 0.0
            reciprocal_ranks.append(rr)

            details.append({
                "query": query,
                "difficulty": difficulty,
                "hit": is_hit,
                "rr": rr,
            })

        n = len(_TEST_CASES)
        return {
            "hit_rate": hits / n if n else 0.0,
            "mrr": statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0.0,
            "details": details,
        }

    def measure_latency(self, queries: List[str], num_runs: int = 3) -> dict:
        retriever = self.vector_service.get_retriever()
        latencies = []
        for query in queries:
            for _ in range(num_runs):
                start = time.perf_counter()
                retriever.invoke(query)
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)

        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        return {
            "avg_ms": statistics.mean(latencies) * 1000,
            "p50_ms": sorted_lat[int(n * 0.50)] * 1000,
            "p95_ms": sorted_lat[int(n * 0.95)] * 1000,
            "p99_ms": sorted_lat[int(n * 0.99)] * 1000,
            "min_ms": sorted_lat[0] * 1000,
            "max_ms": sorted_lat[-1] * 1000,
            "num_samples": n,
        }


def _print_results(eval_result: dict, latency: dict):
    """格式化输出评估结果"""
    details = eval_result["details"]
    hit_rate = eval_result["hit_rate"]
    mrr = eval_result["mrr"]

    # 逐条明细
    print(f"{'查询':<28} {'难度':<8} {'命中':>6} {'RR':>8}")
    print("-" * 52)
    for d in details:
        hit_mark = "OK" if d["hit"] else "--"
        print(f"{d['query']:<28} {d['difficulty']:<8} {hit_mark:>6} {d['rr']:<8.2f}")

    # 按难度分组
    print()
    for diff in ["easy", "medium", "hard"]:
        group = [d for d in details if d["difficulty"] == diff]
        if group:
            g_hits = sum(1 for d in group if d["hit"])
            g_mrr = statistics.mean(d["rr"] for d in group)
            print(f"  [{diff}] Hit Rate: {g_hits}/{len(group)} ({g_hits/len(group):.0%})  MRR: {g_mrr:.2%}")

    # 汇总
    print()
    print(f"  [总计] Hit Rate: {hit_rate:.2%}  ({sum(1 for d in details if d['hit'])}/{len(details)})")
    print(f"  [总计] MRR:      {mrr:.2%}")
    print(f"  [延迟] {latency['avg_ms']:.0f}ms avg | "
          f"p50={latency['p50_ms']:.0f}ms | p95={latency['p95_ms']:.0f}ms | "
          f"min={latency['min_ms']:.0f}ms | max={latency['max_ms']:.0f}ms")


if __name__ == '__main__':
    evaluator = RagEvaluator(auto_seed=True)
    try:
        eval_result = evaluator.evaluate()
        all_queries = [qc[0] for qc in _TEST_CASES]
        latency = evaluator.measure_latency(all_queries, num_runs=2)
        _print_results(eval_result, latency)
    finally:
        evaluator.cleanup_test_data()
