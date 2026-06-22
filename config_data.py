import os

md5_path = "./data/md5.text"

# Chroma
collection_name = "rag"
persist_directory = "./data/chroma_db"

# splitter
chunk_size = 100                                                # 分割后的文本段最大长度
chunk_overlap = 20                                              # 连续文本段之间的字符重叠数量
separators = ["\n\n", "\n", ".", "!", "?", "。", "！", "？", " ", ""]  # 自然段落划分的符号
min_split_char_number = 1000                                    # 触发文本分割的阈值

retriever_k = 3                                                 # 检索返回的文档数量

embedding_model_name = "text-embedding-v4"
chat_model_name = "qwen3-max"

# Agent 配置
AGENT_SYSTEM_PROMPT = (
    "你是一个智能客服助手。你必须使用工具来回答用户问题，不能直接回答。\n\n"
    "可用工具：\n"
    "1. knowledge_base_search: 在本地知识库中搜索。查询产品知识、FAQ、文档内容时使用此工具。\n"
    "2. web_search: 在互联网上搜索。当用户询问新闻、实时信息、或知识库无结果时，使用此工具。\n"
    "3. calculator: 执行数学计算。当用户需要计算时使用此工具。\n\n"
    "规则：\n"
    "- 每次回答前必须先调 knowledge_base_search 搜索知识库，无论问题看起来是否相关\n"
    "- 知识库无结果且需要实时信息 → 调 web_search\n"
    "- 用户要求计算 → 调 calculator\n"
    "- 第一个工具没结果 → 试试其他工具\n"
    "- 用中文回答，注明信息来源\n\n"
    "以下情况必须明确拒绝回答：\n"
    "- 违反法律法规、伦理道德、黄赌毒、暴力恐怖、政治敏感的问题\n"
    "- 要求执行物理动作（如发邮件、下单、控制设备）或调用外部OA系统（我没有这些权限）\n"
    "- 所有工具都无结果，且问题超出我的知识范围"
)
agent_max_iterations = 5            # Agent 最大工具调用轮数
agent_verbose = True                # 是否打印工具调用日志

# Web search
web_search_max_results = 5

# API
api_host = "0.0.0.0"
api_port = 8000

# OCR Configuration
ocr_language = "ch"                      # PaddleOCR lang 参数（"ch" 支持中英文）
ocr_confidence_threshold = 0.5           # PaddleOCR 置信度阈值，低于该值的结果将被丢弃

# Auth — 双角色，密码只在 .env 中配置，Python 代码零硬编码
admin_token = os.environ["ADMIN_TOKEN"]   # 必须在 .env 中配置，否则启动失败
guest_token = os.environ["GUEST_TOKEN"]   # 必须在 .env 中配置，否则启动失败
guest_daily_limit = 10                     # guest 每日提问次数上限
