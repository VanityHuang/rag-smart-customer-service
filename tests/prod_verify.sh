#!/usr/bin/env bash
# 生产环境自动化验证脚本
# 用法: bash tests/prod_verify.sh [BASE_URL] [TOKEN]
#
# 示例:
#   bash tests/prod_verify.sh                                  # 用默认值（需设置 RAG_PROD_URL / RAG_TEST_TOKEN）
#   bash tests/prod_verify.sh https://your-domain.com/rag &lt;your-token&gt;

set -euo pipefail

# ── 参数 ──
BASE_URL="${1:-${RAG_PROD_URL:?Error: 请提供 BASE_URL 参数或设置 RAG_PROD_URL 环境变量}}"
TOKEN="${2:-${RAG_TEST_TOKEN:?Error: 请提供 TOKEN 参数或设置 RAG_TEST_TOKEN 环境变量}}"
AUTH="Authorization: Bearer ${TOKEN}"

PASS=0
FAIL=0
SKIP=0

# ── 工具函数 ──
check() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        echo "  ✅ ${desc} (HTTP ${actual})"
        PASS=$((PASS + 1))
    else
        echo "  ❌ ${desc} — 期望 ${expected}，实际 ${actual}"
        FAIL=$((FAIL + 1))
    fi
}

section() {
    echo ""
    echo "━━━ $1 ━━━"
}

# ── 开始 ──
echo "🎯 生产环境验证: ${BASE_URL}"
echo "   时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ── 1. 前端页面 ──
section "前端页面"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/" --max-time 10 2>/dev/null || echo "000")
check "聊天页面可达" "200" "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/upload.html" --max-time 10 2>/dev/null || echo "000")
check "知识库管理页面可达" "200" "$CODE"

# ── 2. 认证 ──
section "认证"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/chat/sessions" --max-time 10 2>/dev/null || echo "000")
check "无 token → 401" "401" "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/chat/sessions" \
    -H "Authorization: Bearer wrong_token" --max-time 10 2>/dev/null || echo "000")
check "错误 token → 401" "401" "$CODE"

# ── 3. 聊天 API ──
section "聊天 API"
RESP=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/chat" \
    -H "Content-Type: application/json" \
    -H "${AUTH}" \
    -d '{"message": "你好", "session_id": "prod_verify"}' \
    --max-time 30 2>/dev/null)
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
check "POST /api/chat → 200" "200" "$CODE"

# 验证 token_usage 字段
if echo "$BODY" | grep -q "token_usage"; then
    echo "  ✅ 响应包含 token_usage 字段"
    PASS=$((PASS + 1))
else
    echo "  ⚠️  响应未包含 token_usage 字段"
    SKIP=$((SKIP + 1))
fi

# ── 4. SSE 流式 ──
section "SSE 流式"
HEADERS=$(curl -s -D - -o /dev/null -X POST "${BASE_URL}/api/chat/stream" \
    -H "Content-Type: application/json" \
    -H "${AUTH}" \
    -d '{"message": "1+1=?", "session_id": "prod_verify"}' \
    --max-time 30 2>/dev/null)
CODE=$(echo "$HEADERS" | head -1 | grep -oP '\d{3}' | head -1)
check "POST /api/chat/stream → 200" "200" "$CODE"

if echo "$HEADERS" | grep -qi "text/event-stream"; then
    echo "  ✅ Content-Type: text/event-stream"
    PASS=$((PASS + 1))
else
    echo "  ❌ Content-Type 不是 text/event-stream"
    FAIL=$((FAIL + 1))
fi

# ── 5. 会话管理 ──
section "会话管理"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/chat/sessions" \
    -H "${AUTH}" --max-time 10 2>/dev/null || echo "000")
check "GET /api/chat/sessions → 200" "200" "$CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    "${BASE_URL}/api/chat/history?session_id=prod_verify" \
    -H "${AUTH}" --max-time 10 2>/dev/null || echo "000")
check "GET /api/chat/history → 200" "200" "$CODE"

# ── 6. 知识库 ──
section "知识库"
CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/knowledge-base/documents" \
    -H "${AUTH}" --max-time 10 2>/dev/null || echo "000")
check "GET /api/knowledge-base/documents → 200" "200" "$CODE"

# 上传测试文件
TMPFILE=$(mktemp /tmp/prod_verify_XXXXXX.txt)
echo "生产验证测试文档 $(date +%s)" > "$TMPFILE"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "${BASE_URL}/api/knowledge-base/upload" \
    -H "${AUTH}" \
    -F "file=@${TMPFILE}" \
    --max-time 30 2>/dev/null || echo "000")
rm -f "$TMPFILE"
check "POST /api/knowledge-base/upload → 200" "200" "$CODE"

# ── 7. Docker 容器状态 ──
section "Docker 容器"
if command -v docker &>/dev/null; then
    STATUS=$(sudo docker compose -f /home/admin/my_projects/RAG/docker/docker-compose.yml ps --format json 2>/dev/null | grep -oP '"State":"[^"]*"' | head -1 || echo "")
    if echo "$STATUS" | grep -qi "running"; then
        echo "  ✅ 容器状态: running"
        PASS=$((PASS + 1))
    else
        echo "  ❌ 容器未运行: ${STATUS}"
        FAIL=$((FAIL + 1))
    fi
else
    echo "  ⏭️  docker 命令不可用，跳过容器检查"
    SKIP=$((SKIP + 1))
fi

# ── 汇总 ──
echo ""
echo "━━━ 验证结果 ━━━"
echo "  ✅ 通过: ${PASS}"
echo "  ❌ 失败: ${FAIL}"
echo "  ⏭️  跳过: ${SKIP}"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo "❌ 存在失败项，请检查！"
    exit 1
else
    echo "✅ 全部通过"
    exit 0
fi
