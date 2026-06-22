"""认证中间件 — 验证 token 并设置 request.state.role"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from api.auth import get_user_role


class AuthRoleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # OPTIONS 预检放行
        if request.method == "OPTIONS":
            return await call_next(request)

        # 提取 Bearer token
        auth_header = request.headers.get("authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        role = get_user_role(token)
        if not role:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing authorization token"})

        request.state.role = role
        return await call_next(request)
