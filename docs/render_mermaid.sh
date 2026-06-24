#!/usr/bin/env bash
# 用 mermaid-cli (mmdc) 将 Mermaid .md 文件渲染为 PNG
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIAGRAMS_DIR="$SCRIPT_DIR/diagrams"

# Puppeteer 配置（无头 Chrome + no-sandbox）
PUPPETEER_CFG=$(mktemp /tmp/puppeteer_XXXXXX.json)
cat > "$PUPPETEER_CFG" <<'EOF'
{
  "executablePath": "/usr/bin/google-chrome",
  "args": ["--no-sandbox", "--disable-gpu", "--disable-software-rasterizer"]
}
EOF

# Mermaid 配置
MERMAID_CFG=$(mktemp /tmp/mermaid_cfg_XXXXXX.json)
cat > "$MERMAID_CFG" <<'EOF'
{
  "theme": "default",
  "themeVariables": {
    "fontSize": "14px"
  },
  "flowchart": {
    "useMaxWidth": false,
    "htmlLabels": true
  },
  "sequence": {
    "useMaxWidth": false
  }
}
EOF

echo "Rendering diagrams with mermaid-cli..."
echo ""

for md_file in "$DIAGRAMS_DIR"/*.md; do
    [ -f "$md_file" ] || continue
    basename="$(basename "$md_file" .md)"
    [ "$basename" = "README" ] && continue

    echo -n "  $basename ... "

    output="$DIAGRAMS_DIR/${basename}.png"

    npx --yes @mermaid-js/mermaid-cli \
        -i "$md_file" \
        -o "$output" \
        -b white \
        -s 2 \
        -c "$MERMAID_CFG" \
        -p "$PUPPETEER_CFG" \
        -q \
        2>/dev/null

    # mmdc 有时给输出加 -1 后缀，统一重命名
    actual=$(ls "${DIAGRAMS_DIR}/${basename}"*.png 2>/dev/null | head -1)
    if [ -n "$actual" ] && [ "$actual" != "$output" ]; then
        mv "$actual" "$output"
    fi

    if [ -f "$output" ]; then
        dims=$(identify -format "%wx%h" "$output" 2>/dev/null || echo "?")
        size=$(stat -c%s "$output")
        echo "✓  ${dims}  ($(( size / 1024 ))KB)"
    else
        echo "✗ 失败"
    fi
done

rm -f "$PUPPETEER_CFG" "$MERMAID_CFG"

echo ""
echo "All PNGs:"
ls -lh "$DIAGRAMS_DIR"/*.png 2>/dev/null
