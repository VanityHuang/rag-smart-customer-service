"""角色认证 — 根据 Bearer token 识别 admin / guest"""
import config_data as config


def get_user_role(token: str) -> str:
    """返回角色字符串：'admin' 或 'guest'。无效 token 返回空字符串。"""
    if token == config.admin_token:
        return "admin"
    if token == config.guest_token:
        return "guest"
    return ""
