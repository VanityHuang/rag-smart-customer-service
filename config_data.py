"""
全局配置 — 集中管理所有可调参数

注释标记说明：
  [核心]    — 影响 Agent 行为，调优重点
  [稳定]    — 很少变动
  [fallback] — API 层已按角色传独立路径，此处仅作默认值
  [废弃]    — 不再使用，保留供参考
"""
import os

# ── 文本分割 ──
chunk_size = 100                                                # [稳定] 分割后的文本段最大长度
chunk_overlap = 20                                              # [稳定] 连续文本段之间的字符重叠数量
separators = ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]  # [稳定] 自然段落划分符号
min_split_char_number = 1000                                    # [稳定] 文档小于此字符数不触发分割

# ── 检索 ──
retriever_k = 3                                                 # [稳定] 每次检索返回的文档数量
score_high = 0.2                                                # [核心] 余弦距离 < 0.2（相似度 > 0.8）：高分命中，直接用知识库
score_low = 0.5                                                 # [核心] 余弦距离 < 0.5（相似度 > 0.5）：中分模糊，知识库 + 联网补充
retriever_score_threshold = 0.5                                 # [fallback] get_retriever_with_score 默认阈值

# ── 模型 ──
embedding_model_name = "text-embedding-v4"                      # [稳定] 阿里云嵌入模型
chat_model_name = "qwen3-max"                                   # [稳定] 阿里云对话模型

# ── Agent ──
AGENT_SYSTEM_PROMPT = (                                         # [核心] 系统提示词
    "你是一个智能客服助手。你必须使用工具来回答用户问题，不能直接回答。\n\n"
    "可用工具：\n"
    "1. knowledge_base_search: 在本地知识库中搜索。查询产品知识、FAQ、文档内容时使用此工具。\n"
    "2. web_search: 在互联网上搜索。当用户询问新闻、实时信息、或知识库无结果时，使用此工具。\n"
    "3. calculator: 执行数学计算。当用户需要计算时使用此工具。\n\n"
    "规则：\n"
    "- 每次回答前必须先调 knowledge_base_search 搜索知识库，无论问题看起来是否相关\n"
    "- 知识库有结果时，必须以知识库内容为主要依据回答，联网搜索结果仅作补充\n"
    "- 知识库无结果且需要实时信息 → 调 web_search\n"
    "- 用户要求计算 → 调 calculator\n"
    "- 第一个工具没结果 → 试试其他工具\n"
    "- 用中文回答，注明信息来源\n\n"
    "以下情况必须明确拒绝回答：\n"
    "- 违反法律法规、伦理道德、黄赌毒、暴力恐怖、政治敏感的问题\n"
    "- 要求执行物理动作（如发邮件、下单、控制设备）或调用外部OA系统（我没有这些权限）\n"
    "- 所有工具都无结果，且问题超出我的知识范围"
)
agent_max_iterations = 5                                        # [稳定] Agent 最大工具调用轮数
agent_verbose = True                                            # [稳定] 是否打印工具调用日志

# ── 联网搜索 ──
web_search_max_results = 5                                      # [稳定] 联网搜索返回的最大结果数

# ── API ──
api_host = "0.0.0.0"                                            # [稳定] uvicorn 监听地址
api_port = 8000                                                 # [稳定] uvicorn 监听端口

# ── 认证 ──
admin_token = os.environ["ADMIN_TOKEN"]                         # [稳定] 管理员密码（从 .env 注入）
guest_token = os.environ["GUEST_TOKEN"]                         # [稳定] 访客密码（从 .env 注入）
guest_daily_limit = 10                                          # [稳定] 访客每小时提问次数上限

# ── 知识库存储（fallback 默认值）──
md5_path = "./data/md5.txt"                                     # [fallback] API 层按角色传独立路径
collection_name = "rag"                                         # [fallback] API 层按角色传独立 collection
persist_directory = "./data/chroma_db"                          # [fallback] API 层按角色传独立目录
