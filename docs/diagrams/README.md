# RAG 系统架构图

本项目包含 7 张 Mermaid 格式架构图，每张图独立一个 .md 文件，方便单独导出。

| 文件 | 内容 |
|------|------|
| [`architecture_frontend.md`](architecture_frontend.md) | 前端 + nginx反代 + FastAPI接口层 |
| [`architecture_backend.md`](architecture_backend.md) | 服务层 + 基础设施层 + 外部服务 |
| [`module_dependency.md`](module_dependency.md) | Python 模块 import 依赖链 |
| [`data_flow_upload.md`](data_flow_upload.md) | 知识库导入：文件→解析→去重→分块→嵌入→存储 |
| [`data_flow_qa.md`](data_flow_qa.md) | Agent 问答：提问→工具调用→流式生成 |
| [`data_flow_sse.md`](data_flow_sse.md) | SSE 端到端时序：浏览器→nginx→FastAPI→Agent→DashScope |
| [`deployment.md`](deployment.md) | 生产部署：Internet→nginx→Docker→systemd→外部服务 |

## 查看方式

1. **GitHub**: 上传后 Markdown 中的 mermaid 代码块自动渲染
2. **VS Code**: 安装 `Markdown Preview Mermaid Support` 插件，打开 .md 预览
3. **Typora**: 直接打开 .md，自动渲染
4. **导出**: 复制代码到 [mermaid.live](https://mermaid.live/) 可导出 PNG/SVG
