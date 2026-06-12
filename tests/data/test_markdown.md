# 产品使用手册

## 简介

本产品是一个**智能客服系统**，支持以下功能：

- 知识库检索
- 联网搜索
- 数学计算

## 安装步骤

1. 克隆仓库到本地
2. 安装依赖：`pip install -r requirements.txt`
3. 设置 API Key：`export DASHSCOPE_API_KEY=sk-xxxxxx`
4. 启动服务：`streamlit run ui/app_qa.py`

## 常用命令

| 命令 | 说明 |
|------|------|
| `streamlit run ui/app_qa.py` | 启动问答界面 |
| `python -m pytest tests/` | 运行测试 |
| `docker-compose up --build` | Docker 部署 |

## 注意事项

> 请确保 API Key 已正确配置，否则服务无法启动。
> 建议在生产环境中使用 Docker 部署。

## 示例代码

```python
from rag_agent import RagAgentService

service = RagAgentService()
response = service.invoke("你好，介绍一下自己")
print(response)
```

更多信息请访问 [项目主页](https://github.com/example/rag)。
