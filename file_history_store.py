import datetime
import json
import os
import threading
from typing import Sequence

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import message_to_dict, BaseMessage, messages_from_dict

STORAGE_PATH = "./data/chat_history"


def get_history(session_id):
    return FileChatMessageHistory(session_id, STORAGE_PATH)


# ── 会话元数据注册表 ──

_metadata_lock = threading.Lock()


class SessionsMetadata:
    """管理 sessions_metadata.json — 所有会话的标题和时间戳注册表"""

    def __init__(self, storage_path=STORAGE_PATH):
        self.storage_path = storage_path
        self.metadata_path = os.path.join(storage_path, "sessions_metadata.json")
        os.makedirs(os.path.dirname(self.metadata_path), exist_ok=True)
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.metadata_path):
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _read(self) -> dict:
        with _metadata_lock:
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return {}

    def _write(self, data: dict):
        with _metadata_lock:
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def create_session(self, session_id: str):
        data = self._read()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        data[session_id] = {
            "title": "新对话",
            "created_at": now,
            "updated_at": now,
        }
        self._write(data)

    def list_sessions(self) -> list:
        data = self._read()
        items = []
        for sid, meta in data.items():
            items.append({
                "session_id": sid,
                "title": meta.get("title", "新对话"),
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
            })
        items.sort(key=lambda x: x["updated_at"], reverse=True)
        return items

    def get_session(self, session_id: str) -> dict | None:
        return self._read().get(session_id)

    def update_session(self, session_id: str, title: str = None, updated_at: str = None):
        data = self._read()
        if session_id in data:
            if title is not None:
                data[session_id]["title"] = title
            if updated_at is not None:
                data[session_id]["updated_at"] = updated_at
            self._write(data)

    def delete_session(self, session_id: str):
        data = self._read()
        data.pop(session_id, None)
        self._write(data)

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._read()


_metadata_store = None


def get_metadata_store() -> SessionsMetadata:
    global _metadata_store
    if _metadata_store is None:
        _metadata_store = SessionsMetadata()
    return _metadata_store


def touch_session_metadata(session_id: str, first_user_message: str = None, title: str = None):
    """更新会话元数据。首次消息时注册，每次更新 updated_at。
    title 参数由调用方（LLM 生成）传入。
    """
    store = get_metadata_store()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if not store.session_exists(session_id):
        store.create_session(session_id)

    if title:
        store.update_session(session_id, title=title, updated_at=now)
    else:
        store.update_session(session_id, updated_at=now)


# ── 文件聊天历史 ──


class FileChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, session_id, storage_path=STORAGE_PATH):
        self.session_id = session_id
        self.storage_path = storage_path
        self.file_path = os.path.join(self.storage_path, self.session_id)
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        all_messages = list(self.messages)
        all_messages.extend(messages)
        new_messages = [message_to_dict(message) for message in all_messages]
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(new_messages, f)

    @property
    def messages(self) -> list[BaseMessage]:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                messages_data = json.load(f)
                return messages_from_dict(messages_data)
        except FileNotFoundError:
            return []

    def clear(self) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump([], f)

