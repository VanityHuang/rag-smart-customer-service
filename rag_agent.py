"""
RAG Agent Service — 基于 Function Calling 的自定义 Agent 循环
使用 ChatTongyi.bind_tools() + 手动迭代循环，0 额外依赖
"""
import logging

from langchain_community.chat_models import ChatTongyi
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, ToolMessage
)
from langchain_core.tools import tool

import config_data as config
from file_history_store import get_history, touch_session_metadata
from vector_stores import VectorStoreService

logger = logging.getLogger(__name__)

# 对话轮次截断配置
MAX_HISTORY_ROUNDS = 5  # 保留最近 5 轮对话（10 条消息：5 human + 5 ai）


class RagAgentService:
    def __init__(self, vector_service: VectorStoreService = None, role: str = "admin"):
        self.role = role
        self.vector_service = vector_service or VectorStoreService(
            embedding=config.get_embedding_model()
        )
        self.chat_model = ChatTongyi(
            model=config.chat_model_name,
            temperature=0,
            streaming=True,
        )
        self.tools = self._create_tools()
        self.tool_map = {t.name: t for t in self.tools}
        self.model_with_tools = self.chat_model.bind_tools(self.tools)
        # Token 用量追踪（每次请求重置）
        self._total_usage = {"input_tokens": 0, "output_tokens": 0}

    def _track_usage(self, response):
        """累加 LLM 调用的 token 用量"""
        usage = getattr(response, "usage_metadata", None)
        if usage:
            inp = getattr(usage, "input_tokens", 0) or 0
            out = getattr(usage, "output_tokens", 0) or 0
            self._total_usage["input_tokens"] += inp
            self._total_usage["output_tokens"] += out
            return

        # 兼容：尝试从 response_metadata 中提取（部分模型提供商）
        meta = getattr(response, "response_metadata", None)
        if meta and isinstance(meta, dict):
            usage_info = meta.get("usage") or meta.get("token_usage") or {}
            self._total_usage["input_tokens"] += usage_info.get("prompt_tokens", 0) or usage_info.get("input_tokens", 0)
            self._total_usage["output_tokens"] += usage_info.get("completion_tokens", 0) or usage_info.get("output_tokens", 0)
            return

        logger.debug(f"_track_usage: 无法提取 token 用量, response 类型={type(response).__name__}")

    @property
    def token_usage(self) -> dict:
        """返回本次请求的 token 用量明细"""
        return dict(self._total_usage)

    def _truncate_history(self, history_messages: list) -> list:
        """按轮次截断历史消息，保留最近 MAX_HISTORY_ROUNDS 轮对话"""
        if not history_messages:
            return []
        # 每轮 = 1 human + 1 ai = 2 条消息，保留最近 N 轮
        max_messages = MAX_HISTORY_ROUNDS * 2
        if len(history_messages) <= max_messages:
            return history_messages
        return history_messages[-max_messages:]

    def _create_tools(self):
        """定义 Agent 可用的三个工具"""
        vector_service = self.vector_service  # 闭包捕获

        @tool
        def knowledge_base_search(query: str) -> str:
            """在本地知识库中搜索相关信息。当用户询问关于已有文档、产品知识、FAQ等内容时，优先使用此工具。"""
            try:
                # 相似度搜索（带分数）
                results = vector_service.vector_store.similarity_search_with_score(
                    query, k=config.retriever_k
                )
                if not results:
                    return "【知识库】未找到相关信息。"

                # 按分数分层（余弦距离，越小越相似）
                high_docs = []   # 距离 < 0.2（相似度 > 0.8）：高分命中
                mid_docs = []    # 距离 0.2~0.5（相似度 0.5~0.8）：中分模糊
                for doc, score in results:
                    if score < config.score_high:
                        high_docs.append(doc)
                    elif score < config.score_low:
                        mid_docs.append(doc)
                    # >=1.5 距离太远，丢弃

                # 组装知识库结果
                parts = []
                for doc in high_docs + mid_docs:
                    source = doc.metadata.get("source", "未知来源")
                    score_val = round(1 - doc.metadata.get("score", 0), 2) if "score" in doc.metadata else "?"
                    parts.append(f"[来源: {source}]\n{doc.page_content}")

                kb_result = "\n\n".join(parts) if parts else ""

                # 中分模糊 → 触发联网搜索补充
                if mid_docs and not high_docs:
                    web_results = _web_search_impl(query)
                    if web_results:
                        kb_result += f"\n\n【联网搜索补充】\n{web_results}"

                return kb_result if kb_result else "【知识库】未找到相关信息。"
            except Exception as e:
                return f"【知识库】搜索出错: {str(e)}"

        def _web_search_impl(query: str) -> str:
            """联网搜索内部实现（供 knowledge_base_search 和 web_search 共用）"""
            import requests
            from lxml import html

            USER_AGENT = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

            def _bing_search(q: str) -> list:
                results = []
                try:
                    resp = requests.get(
                        "https://cn.bing.com/search",
                        params={"q": q, "count": config.web_search_max_results},
                        headers={"User-Agent": USER_AGENT},
                        timeout=10,
                    )
                    resp.raise_for_status()
                    tree = html.fromstring(resp.text)
                    for li in tree.xpath("//li[contains(@class, 'b_algo')]"):
                        title_el = li.xpath(".//h2/a")
                        snippet_el = li.xpath(".//div[contains(@class, 'b_caption')]/p")
                        if title_el:
                            title = title_el[0].text_content().strip()
                            url = title_el[0].get("href", "")
                            snippet = snippet_el[0].text_content().strip() if snippet_el else ""
                            results.append(f"[{title}]({url})\n{snippet}")
                except Exception:
                    pass
                return results

            def _baidu_news_search(q: str) -> list:
                results = []
                try:
                    resp = requests.get(
                        "https://news.baidu.com/ns",
                        params={"word": q, "pn": 0, "rn": config.web_search_max_results},
                        headers={
                            "User-Agent": USER_AGENT,
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        },
                        timeout=10,
                    )
                    resp.raise_for_status()
                    tree = html.fromstring(resp.text)
                    for div in tree.xpath("//div[contains(@class, 'result-op')]"):
                        title_el = div.xpath(".//h3[contains(@class, 'news-title')]/a"
                                            "|.//a[contains(@class, 'news-title-font')]")
                        if not title_el:
                            continue
                        title = title_el[0].text_content().strip()
                        url = title_el[0].get("href", "")
                        snippet_el = div.xpath(
                            ".//*[contains(@class, 'c-abstract')]"
                            "|.//*[contains(@class, 'c-span-last')]"
                        )
                        snippet = snippet_el[0].text_content().strip() if snippet_el else ""
                        source_el = div.xpath(".//*[contains(@class, 'news-source')]")
                        source = source_el[0].text_content().strip() if source_el else ""
                        entry = f"[{title}]({url})\n{snippet}"
                        if source:
                            entry += f"\n来源: {source}"
                        results.append(entry)
                except Exception:
                    pass
                return results

            try:
                results = _baidu_news_search(query)
                if results:
                    return "\n\n".join(results)
                results = _bing_search(query)
                if results:
                    return "\n\n".join(results)
                return "【网络搜索】未找到相关结果。"
            except Exception as e:
                return f"【网络搜索】失败: {str(e)}"

        @tool
        def web_search(query: str) -> str:
            """从互联网搜索最新信息。当知识库中没有相关信息，或需要查询实时信息（新闻、天气、最新动态）时使用此工具。"""
            return _web_search_impl(query)

        @tool
        def calculator(expression: str) -> str:
            """执行数学计算。输入应为数学表达式，如 '2 + 2' 或 '3 * 4 / 2' 或 'sqrt(16)'。"""
            import ast
            import math
            import operator as op

            allowed_ops = {
                ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
                ast.Div: op.truediv, ast.Pow: op.pow, ast.USub: op.neg,
                ast.Mod: op.mod, ast.FloorDiv: op.floordiv,
            }
            allowed_funcs = {"abs": abs, "round": round, "min": min, "max": max}

            try:
                tree = ast.parse(expression.strip(), mode='eval')

                def _eval(node):
                    if isinstance(node, ast.Expression):
                        return _eval(node.body)
                    elif isinstance(node, ast.Constant):
                        if isinstance(node.value, (int, float)):
                            return node.value
                        raise ValueError("不支持的数据类型")
                    elif isinstance(node, ast.BinOp):
                        return allowed_ops[type(node.op)](_eval(node.left), _eval(node.right))
                    elif isinstance(node, ast.UnaryOp):
                        return allowed_ops[type(node.op)](_eval(node.operand))
                    elif isinstance(node, ast.Call):
                        func_name = node.func.id if isinstance(node.func, ast.Name) else ""
                        if func_name == "sqrt":
                            return math.sqrt(_eval(node.args[0]))
                        if func_name in allowed_funcs:
                            return allowed_funcs[func_name](*[_eval(a) for a in node.args])
                        raise ValueError(f"未知函数: {func_name}")
                    else:
                        raise ValueError(f"不支持的语法")

                result = _eval(tree)
                return f"计算结果: {expression} = {result}"
            except Exception as e:
                return f"【计算器】错误: {str(e)}"

        return [knowledge_base_search, web_search, calculator]

    def _execute_agent_loop(self, messages: list) -> AIMessage:
        """
        自定义 Agent 迭代循环
        1. 调用绑定了工具的模型
        2. 有 tool_calls 则执行工具 -> 追加 ToolMessage -> 继续循环
        3. 无 tool_calls 则返回最终回答
        """
        max_iter = config.agent_max_iterations

        for iteration in range(max_iter):
            if config.agent_verbose:
                logger.debug(f"Agent iteration {iteration + 1}/{max_iter}")

            response = self.model_with_tools.invoke(messages)
            self._track_usage(response)

            if not response.tool_calls:
                return response  # 最终回答（包括拒答）

            # 追加 AI 的工具调用消息到历史
            messages.append(response)

            # 执行每个工具调用
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id = tc["id"]

                if config.agent_verbose:
                    logger.info(f"  调用工具: {tool_name}({tool_args})")

                if tool_name not in self.tool_map:
                    result = f"未知工具: {tool_name}"
                else:
                    try:
                        result = self.tool_map[tool_name].invoke(tool_args)
                    except Exception as e:
                        result = f"工具执行错误 ({tool_name}): {str(e)}"

                messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

        # 达到最大迭代次数，强制不带工具调用生成最终回答
        fallback_msg = SystemMessage(
            content="你已经达到了最大工具调用次数。请基于已获得的信息给出最终回答。"
        )
        messages.append(fallback_msg)
        return self.chat_model.invoke(messages)

    def _generate_title(self, first_message: str) -> str:
        """用 LLM 生成简短会话标题（≤20 字），失败时降级为截断"""
        prompt = (
            "根据以下对话的第一条用户消息，生成一个简短的中文标题"
            "（不超过20个字），直接返回标题，不要加引号或解释。\n"
            f"消息：{first_message}"
        )
        try:
            resp = self.chat_model.invoke(prompt)
            title = resp.content.strip()
            if len(title) > 20:
                title = title[:20] + "…"
            return title
        except Exception:
            title = first_message.strip()
            return title[:40] + "…" if len(title) > 40 else title

    def _maybe_auto_title(self, session_id: str, first_message: str, history):
        """如果会话刚创建（metadata 中不存在或 title 为 '新对话'），用 LLM 生成标题"""
        from file_history_store import get_metadata_store
        store = get_metadata_store(self.role)
        meta = store.get_session(session_id)
        if meta is None or meta.get("title") == "新对话":
            title = self._generate_title(first_message)
            touch_session_metadata(session_id, title=title, role=self.role)
        else:
            touch_session_metadata(session_id, role=self.role)

    def invoke(self, message: str, session_id: str = "user_001") -> str:
        """处理用户消息并返回 Agent 回答"""
        self._total_usage = {"input_tokens": 0, "output_tokens": 0}
        history = get_history(session_id, self.role)
        user_message = HumanMessage(content=message)

        # Token 预算截断：保留最近的历史消息，防止上下文过长
        full_history = list(history.messages)
        truncated = self._truncate_history(full_history)

        messages = [
            SystemMessage(content=config.AGENT_SYSTEM_PROMPT),
            *truncated,
            user_message,
        ]

        final_response = self._execute_agent_loop(messages)

        history.add_messages([user_message, final_response])

        # 会话元数据：首次消息时 LLM 生成标题
        self._maybe_auto_title(session_id, message, history)

        return final_response.content

    def stream(self, message: str, session_id: str = "user_001"):
        """真正的流式接口 — Agent 循环处理工具调用后，流式输出最终答案

        两阶段设计：
        1. Agent 循环（同步）：用 model_with_tools.invoke 检测 tool_calls
        2. 流式输出（异步）：用 chat_model.stream 逐 token 生成最终答案
        """
        self._total_usage = {"input_tokens": 0, "output_tokens": 0}
        history = get_history(session_id, self.role)
        user_message = HumanMessage(content=message)

        # Token 预算截断
        full_history = list(history.messages)
        truncated = self._truncate_history(full_history)

        messages = [
            SystemMessage(content=config.AGENT_SYSTEM_PROMPT),
            *truncated,
            user_message,
        ]

        # Phase 1: Agent 循环 — 同步处理工具调用
        max_iter = config.agent_max_iterations

        for iteration in range(max_iter):
            if config.agent_verbose:
                logger.debug(f"Agent iteration {iteration + 1}/{max_iter}")

            response = self.model_with_tools.invoke(messages)
            self._track_usage(response)

            if not response.tool_calls:
                break

            # 有工具调用：追加响应和工具结果，继续循环
            messages.append(response)

            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_id = tc["id"]

                if config.agent_verbose:
                    logger.info(f"  调用工具: {tool_name}({tool_args})")

                if tool_name not in self.tool_map:
                    result = f"未知工具: {tool_name}"
                else:
                    try:
                        result = self.tool_map[tool_name].invoke(tool_args)
                    except Exception as e:
                        result = f"工具执行错误 ({tool_name}): {str(e)}"

                messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))
        else:
            # 达到最大迭代次数，追加 fallback 提示
            messages.append(SystemMessage(
                content="你已经达到了最大工具调用次数。请基于已获得的信息给出最终回答。"
            ))

        # Phase 2: 流式输出最终答案（不带工具的模型，纯文本流式生成）
        collected = ""
        for chunk in self.chat_model.stream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                collected += chunk.content
                yield chunk.content

        # Phase 3: 保存完整对话到历史
        final_response = AIMessage(content=collected)
        history.add_messages([user_message, final_response])

        # 会话元数据：首次消息时 LLM 生成标题
        self._maybe_auto_title(session_id, message, history)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    service = RagAgentService()

    while True:
        q = input("\n>>> ")
        if q.lower() in ("exit", "quit", "q"):
            break
        if not q.strip():
            continue
        print(service.invoke(q))
