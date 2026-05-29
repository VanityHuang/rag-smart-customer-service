import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import config_data as config

# 切换 true 以使用 FastAPI 后端（需要先启动 API 服务）
USE_API = False

if USE_API:
    import requests
    API_BASE = f"http://{config.api_host}:{config.api_port}/api"
else:
    from rag_agent import RagAgentService

st.title("智能客服")
st.divider()

if "message" not in st.session_state:
    st.session_state["message"] = [{"role": "assistant", "content": "您好, 我是AI智能助手, 有什么可以帮您?"}]

if "rag" not in st.session_state and not USE_API:
    st.session_state["rag"] = RagAgentService()

for message in st.session_state["message"]:
    st.chat_message(message["role"]).write(message["content"])

prompt = st.chat_input()

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role": "user", "content": prompt})

    with st.spinner("AI助手思考中"):
        if USE_API:
            resp = requests.post(
                f"{API_BASE}/chat",
                json={"message": prompt, "session_id": "user_001"},
            )
            result = resp.json()["response"]
        else:
            result = st.session_state["rag"].invoke(prompt)

    st.chat_message("assistant").write(result)
    st.session_state["message"].append({"role": "assistant", "content": result})
