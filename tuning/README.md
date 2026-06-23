# RAG 参数调优工具

通过系统化遍历关键参数，找到最优的 RAG 检索配置。

## 调优流程

```
步骤 1: tune_chunk_params.py     确定 chunk_size 和 overlap
            ↓
步骤 2: tune_retriever_k.py     确定 retriever_k
            ↓
步骤 3: 修改 config_data.py     写入最终参数
```

> ⚠️ 必须按顺序执行。步骤 2 依赖步骤 1 的结果。

---

## 步骤 1: chunk_size × overlap 遍历

### 做什么

暴力遍历 16 种参数组合（4 种 chunk_size × 4 种 overlap），每种组合：
1. 用临时 Chroma 库重建索引
2. 对 70 题测试集执行向量检索
3. 计算 Hit Rate / MRR / 平均相似度

### 执行

```bash
# 在项目根目录执行
cd ~/my_projects/RAG
python tuning/tune_chunk_params.py
```

无需 API Key，纯本地计算，约 5-10 分钟。

### 参数搜索范围

| 参数 | 候选值 |
|------|--------|
| chunk_size | 128, 256, 512, 1024 |
| overlap | 0, 32, 64, 128 |

### 输出

```
chunk_size overlap chunks 显式HR  隐式HR  噪声HR  MRR     相似度
128        0       320    83%     70%     0%      68.21%  0.7102
128        32      350    85%     72%     0%      70.15%  0.7198
...
256        64      180    90%     80%     0%      75.56%  0.7348  ← 🏆
...

🏆 推荐最佳参数: chunk_size=256, overlap=64
```

### 评判标准

综合评分 = 显式HR×0.4 + 隐式HR×0.3 + (1-噪声HR)×0.2 + MRR×0.1

- 显式 HR 权重最高（核心能力）
- 隐式 HR 次之（推理能力）
- 噪声 HR 越低越好（误召回惩罚）
- MRR 衡量排序质量

### 操作

1. 运行脚本，记录推荐的 chunk_size 和 overlap
2. 修改 `config_data.py`：

```python
chunk_size = 256        # ← 改为推荐值
chunk_overlap = 64      # ← 改为推荐值
```

3. 重启容器：`sudo docker compose -f docker/docker-compose.yml restart`

---

## 步骤 2: retriever_k 调优

### 做什么

分两个阶段：
- **Phase 1（离线）**：扫描 k=1,3,5,7,10，绘制 Hit Rate 收敛曲线，找拐点
- **Phase 2（在线）**：对候选 k 值运行真实 Agent 调用，对比 Token 消耗和回答质量

### 执行

```bash
cd ~/my_projects/RAG

# Phase 1: 离线扫描（无需 Key，约 1 分钟）
python tuning/tune_retriever_k.py --phase offline

# Phase 2: 在线验证（需 Key，约 10-15 分钟）
python tuning/tune_retriever_k.py --phase online --k 3 5 7

# 或全量执行（自动串联 Phase 1 → Phase 2）
python tuning/tune_retriever_k.py
```

### Phase 1 输出

```
k    Hit Rate   曲线
1    72%        ████████████████████████████████████░░░░░░░░░░
3    87%        █████████████████████████████████████████████░░
5    90%        ████████████████████████████████████████████████  ← 拐点
7    91%        █████████████████████████████████████████████████
10   91%        █████████████████████████████████████████████████

🎯 拐点候选 k 值: [5]
```

**拐点**：Hit Rate 增量 < 5% 的第一个 k。再大收益递减，但 Token 成本线性增长。

### Phase 2 输出

```
k    平均Token   输入Token  直接回答  联网兜底  拒答
3    2800        2650       18       8        4
5    3200        3050       20       7        3     ← 🏆 最优平衡
7    3600        3450       20       7        3

🏆 推荐 k=5
   平均 Token: 3200 (输入 3050 / 输出 150)
   直接回答: 20/30
```

### 评判标准

- 在 Hit Rate 达标的前提下，选**平均 Token 最少**的 k
- k 越大 → 检索越多文档 → 输入 Token 越多 → 成本越高
- k=5 比 k=10 省约 30% Token，但 Hit Rate 差距 < 5%

### 操作

1. 运行 Phase 1，观察收敛曲线，确定拐点候选
2. 运行 Phase 2，对比候选 k 的 Token 成本
3. 修改 `config_data.py`：

```python
retriever_k = 5    # ← 改为推荐值
```

4. 重启容器：`sudo docker compose -f docker/docker-compose.yml restart`

---

## 完整调优示例

```bash
cd ~/my_projects/RAG

# 1. 调 chunk_size 和 overlap（约 5-10 分钟）
python tuning/tune_chunk_params.py
# → 输出: chunk_size=256, overlap=64
# → 修改 config_data.py 并重启

# 2. 调 retriever_k（约 15 分钟）
python tuning/tune_retriever_k.py
# → 输出: k=5
# → 修改 config_data.py 并重启

# 3. 跑完整评估验证最终效果
python -m pytest tests/test_rag_retriever.py -v -s    # 离线
python -m pytest tests/test_rag_agent.py -v -s        # 在线
```

---

## 测试集来源

两个脚本共用 70 题测试集（内联在脚本中）：

| 类别 | 数量 | 说明 |
|------|------|------|
| 显式问题 | 30 | 直接检索文档原文 |
| 隐式问题 | 20 | 需要跨文档推理 |
| 域外噪声 | 20 | 闲聊/操作指令 |

测试文档位于 `tests/data/` 目录下的 5 个鸭鸭知识文档。
