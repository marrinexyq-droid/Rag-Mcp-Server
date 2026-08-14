# Marrine RAG MCP Server

这是我维护的本地知识库项目：把 PDF 文档摄取为可检索的向量与关键词索引，再通过命令行或 MCP 工具提供混合检索能力。

当前版本以 Windows 本地开发为主，使用 Chroma 持久化向量数据、Ollama 生成 Embedding，并支持在多个 LLM API 配置之间切换。默认使用 DeepSeek 官方 API 直连，同时保留 VectorEngine 中转方案；所有 API Key 都只从环境变量读取。

> 项目仍处于 `0.1.0` Alpha 阶段。当前仓库是我在开源项目基础上维护和扩展的个人版本，来源与许可见 [NOTICE.md](NOTICE.md)。

## 我在这个版本中完成的内容

- 增加可选择的 LLM Profile：一个配置文件可以保存多个 API 方案。
- 配置并验证 DeepSeek 官方 API 直连，同时保留 VectorEngine OpenAI 兼容端点。
- 将不同 Profile 的密钥映射到独立环境变量，避免把 Key 写进仓库。
- 使用本地 Ollama `nomic-embed-text` 生成 768 维向量。
- 保留 Dense、BM25、RRF 混合检索和可选重排能力。
- 提供文档摄取、命令行查询、MCP stdio 服务及 Streamlit 观测面板。
- 用 GitHub Issues、Milestone 和 Project 管理后续开发。

## 工作流程

```text
PDF 文档
   │
   ▼
解析与分块 ──► 元数据增强 ──► Ollama Embedding ──► Chroma
                                             └──► BM25 索引
                                                       │
用户问题 ──► Dense + Sparse 检索 ──► RRF 融合 ──► 可选重排 ──► 结果与来源
                                                       ▲
                                            CLI / MCP 工具
```

## 环境要求

- Python 3.10–3.12（本地开发使用 Python 3.11）
- [Ollama](https://ollama.com/) 及 `nomic-embed-text` 模型
- 一个可用的 OpenAI 兼容 API，或 DeepSeek API
- Git（仅开发和版本管理需要）

## 快速开始

以下命令在仓库根目录执行。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ollama pull nomic-embed-text
```

设置 DeepSeek Key。这里的值只进入当前用户的环境变量，不要把真实 Key 写入 YAML、提交记录或 Issue。

```powershell
[Environment]::SetEnvironmentVariable(
  "DEEPSEEK_API_KEY",
  "你的 API Key",
  "User"
)
$env:DEEPSEEK_API_KEY = "你的 API Key"
```

如果改用 VectorEngine 中转：

```powershell
[Environment]::SetEnvironmentVariable(
  "VECTORENGINE_API_KEY",
  "你的 API Key",
  "User"
)
$env:VECTORENGINE_API_KEY = "你的 API Key"
```

## 多 API Profile

LLM 配置位于 [`config/settings.yaml`](config/settings.yaml)：

```yaml
llm:
  active_profile: "deepseek-direct"
  temperature: 0.0
  max_tokens: 4096
  profiles:
    vectorengine:
      provider: "openai"
      base_url: "https://api.vectorengine.ai/v1"
      api_key_env: "VECTORENGINE_API_KEY"
      model: "deepseek-v4-flash"

    deepseek-direct:
      provider: "deepseek"
      base_url: "https://api.deepseek.com"
      api_key_env: "DEEPSEEK_API_KEY"
      model: "deepseek-v4-flash"
```

切换服务时只需修改 `active_profile`。`api_key_env` 必须填写环境变量名称，而不是密钥本身。还可以继续添加其他 OpenAI 兼容中转站，每个 Profile 使用不同的名称、端点、模型和环境变量。

## 摄取与查询

先启动 Ollama，然后摄取单个 PDF：

```powershell
python scripts/ingest.py --path .\documents\example.pdf --collection notes
```

摄取目录中的全部 PDF：

```powershell
python scripts/ingest.py --path .\documents --collection notes
```

执行混合检索：

```powershell
python scripts/query.py --query "这批文档的核心内容是什么？" --collection notes
```

需要查看检索中间结果时增加 `--verbose`；临时关闭重排时增加 `--no-rerank`。

## MCP 服务

stdio 服务入口是：

```powershell
python -m src.mcp_server.server
```

可用工具包括：

- `query_knowledge_hub`：检索知识库。
- `list_collections`：列出已有集合。
- `get_document_summary`：读取文档摘要与元数据。

MCP 客户端配置示例（把路径替换为你电脑上的绝对路径）：

```json
{
  "mcpServers": {
    "marrine-rag": {
      "command": "D:\\SelfLearn\\Rag-Mcp-Server\\MODULAR-RAG-MCP-SERVER\\.venv\\Scripts\\python.exe",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "D:\\SelfLearn\\Rag-Mcp-Server\\MODULAR-RAG-MCP-SERVER"
    }
  }
}
```

## 观测面板

```powershell
python scripts/start_dashboard.py
```

默认访问地址为 `http://localhost:8501`，可通过 `--port` 指定其他端口。

## 验证

```powershell
python -m pytest tests/unit/test_config_loading.py tests/unit/test_llm_profiles.py
python -m pytest tests/unit -m "not llm"
```

需要真实调用 API 的测试会产生费用，因此默认开发验证应优先运行不依赖外部服务的测试。DeepSeek 直连已完成真实聊天验证；VectorEngine 已验证可以访问模型列表，但聊天调用仍取决于中转账户余额与模型配额。

## 项目管理

- [GitHub Issues](https://github.com/marrinexyq-droid/Rag-Mcp-Server/issues)：缺陷与任务。
- [v0.1 Local MVP](https://github.com/marrinexyq-droid/Rag-Mcp-Server/milestone/1)：当前里程碑。
- [个人 Project 看板](https://github.com/users/marrinexyq-droid/projects/1)：任务状态管理。

近期重点是完成端到端 RAG 验证、稳定 MCP 客户端接入，并逐步收敛依赖版本带来的测试兼容问题。

## 安全约定

- API Key 只保存在环境变量或本地秘密管理工具中。
- `data/`、日志、缓存、虚拟环境和本地 IDE 文件不会提交。
- 如果密钥曾出现在终端输出、聊天记录或 Git 历史中，应立即在服务商后台轮换。
- 发起真实 LLM 请求前，先确认中转站的余额、模型价格与配额。

## 许可与来源

本项目按 MIT License 发布，详见 [LICENSE](LICENSE)。本仓库包含基于 `jerry-ai-dev/MODULAR-RAG-MCP-SERVER` 的代码及我的后续修改；完整说明见 [NOTICE.md](NOTICE.md)。
