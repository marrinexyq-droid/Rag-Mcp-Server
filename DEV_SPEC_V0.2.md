# Developer Specification v0.2

## 1. 文档状态

| 字段 | 值 |
|---|---|
| 版本 | v0.2 |
| 状态 | 已批准规划，尚未开始实现 |
| 日期 | 2026-08-20 |
| 前置版本 | `DEV_SPEC.md` 阶段 A–I（68/68，100%） |
| 主题 | 阶段 J：单节点容器化与 Streamable HTTP 基线 |

本规格把 `DEV_SPEC.md` 7.1 的“云端部署与后端架构学习”收敛为一个可测试、可回滚的增量。v0.2 先交付可复现的 Linux 容器和远程传输基线，不把尚未具备身份系统的私有知识库直接暴露到公网。

## 2. 目标与非目标

### 2.1 目标

1. 保持现有 stdio MCP 客户端完全兼容。
2. 基于同一套 tools 和协议处理逻辑新增 Streamable HTTP transport。
3. 构建可复现、非 root、无密钥的 Linux 容器镜像。
4. 将 Chroma、BM25、摄取历史、图片和 Trace 持久化到明确的挂载目录。
5. 让容器安全访问宿主机或外部 Ollama，不把模型打进应用镜像。
6. 提供 liveness/readiness、官方 MCP 客户端 E2E 和容器重启持久化验收。
7. 建立 GitHub Actions 离线测试与镜像构建门禁。

### 2.2 非目标

以下内容不在 v0.2 实现范围内：

- 将服务部署到公开 Azure/AWS 地址。
- 自建 OAuth Authorization Server，或临时发明非标准鉴权协议。
- 多租户、水平扩容、共享 Chroma、分布式锁和跨副本缓存一致性。
- 将 Ollama 模型或 DeepSeek API Key 烘焙进镜像。
- Kubernetes、Terraform、自动发布公共镜像。
- 修改现有 RAG 召回、重排或生成策略。

公开云部署必须在后续阶段先确定身份提供方、TLS 终止点、数据持久化后端和成本预算。

## 3. 当前基线与约束

### 3.1 已验证基线

- Python 3.11，依赖由 `uv.lock` 锁定。
- MCP Python SDK `2.0.0`。
- 生产 Server 目前只有 stdio transport。
- `create_mcp_server()` 已集中注册 `query_knowledge_hub`、`list_collections`、`get_document_summary`。
- 默认向量存储为本地 Chroma；BM25、SQLite、图片和 Trace 也写入本地文件。
- Embedding 默认依赖宿主机 Ollama `nomic-embed-text`。
- v0.1 真实链路和离线门禁均已通过。

### 3.2 环境事实

- 开发机已安装 Docker CLI `29.5.2`。
- 规格编写时 Docker Desktop Linux daemon 未启动；实现阶段开始容器验收前必须启动。
- 当前仓库没有 Dockerfile、Compose 文件或 GitHub Actions workflow。

### 3.3 协议约束

- stdio 是本地 MCP Host 启动子进程时使用的 transport，stdout 必须只承载协议消息。
- 远程部署使用 Streamable HTTP；不新增 legacy SSE 实现。
- HTTP 服务必须校验 `Origin`，默认只监听或只映射到本机地址。
- 未完成标准鉴权之前，不允许将 MCP 端口暴露到公网。

## 4. 模块与 seam 设计

### 4.1 唯一 Server 组装 Module

`create_mcp_server()` 继续是 tools 与协议处理的唯一组装 Module。它的 interface 不感知 stdio、HTTP、Docker 或云平台。

删除这个 Module 会迫使每个 transport 重复注册 tools 和错误处理，因此它具备足够 Depth；v0.2 不另建第二套 tool server。

### 4.2 Transport seam

在组装好的低层 MCP `Server` 外建立 transport seam：

```text
                          ┌────────────────────────────┐
MCP Client ──────────────►│ Transport Adapter          │
                          │ stdio | Streamable HTTP    │
                          └─────────────┬──────────────┘
                                        │
                          ┌─────────────▼──────────────┐
                          │ create_mcp_server()         │
                          │ tools + protocol handlers   │
                          └─────────────┬──────────────┘
                                        │
                          ┌─────────────▼──────────────┐
                          │ RAG / storage Modules       │
                          └────────────────────────────┘
```

两个 Adapter 共享同一个 Server Module：

- `stdio` Adapter：保留现有行为，作为本地默认值。
- `streamable-http` Adapter：调用 SDK 的 `server.streamable_http_app()`，由 ASGI Server 承载。

Transport 只负责连接、生命周期与安全设置，不得复制 tool schema 或业务逻辑。

### 4.3 运行时 interface

运行时对调用者公开一个小 interface：

```text
run_server(RuntimeOptions) -> exit_code
```

`RuntimeOptions` 至少包含：

- `transport`: `stdio | streamable-http`
- `host`
- `port`
- `mcp_path`
- `allowed_origins`

配置优先级固定为：命令行参数 > 环境变量 > YAML > 安全默认值。stdio 默认行为必须在没有新增配置时保持不变。

建议新增配置：

```yaml
server:
  transport: "stdio"
  http:
    host: "127.0.0.1"
    port: 8000
    mcp_path: "/mcp"
    json_response: true
    stateless: true
    allowed_origins:
      - "http://127.0.0.1:8000"
      - "http://localhost:8000"
```

对应环境变量只承载运行环境差异，不承载密钥：

- `RAG_MCP_TRANSPORT`
- `RAG_MCP_HTTP_HOST`
- `RAG_MCP_HTTP_PORT`
- `RAG_MCP_HTTP_PATH`
- `RAG_MCP_ALLOWED_ORIGINS`

Provider 密钥继续只使用各 Profile 的 `api_key_env`，例如 `DEEPSEEK_API_KEY`。

### 4.4 状态与外部依赖

容器内约定：

| 类型 | 容器路径 | 持久化 |
|---|---|---|
| Chroma / BM25 / SQLite | `/app/data` | 必须挂载 |
| 图片 | `/app/data/images` | 必须挂载 |
| Trace / 日志 | `/app/logs` | 必须挂载 |
| 配置与 prompts | `/app/config` | 镜像内只读，可被显式覆盖 |

Ollama 是 true external dependency。容器镜像不负责启动或下载模型：

- Docker Desktop 默认通过 `host.docker.internal` 访问宿主机 Ollama。
- Linux Engine 通过显式 host gateway 或外部服务地址连接。
- `embedding.base_url` 必须可配置，且 readiness 只做短超时连通性检查，不触发模型下载。

Chroma 本地持久化意味着 v0.2 只支持单实例。任何水平扩容都必须先更换共享存储 Adapter 或重新设计一致性策略。

## 5. HTTP 健康与安全约定

### 5.1 Endpoints

- `/mcp`：Streamable HTTP MCP endpoint。
- `/healthz`：只检查进程与事件循环，不访问 LLM、Ollama 或付费接口。
- `/readyz`：检查配置可加载、状态目录可读写、Ollama endpoint 可达；绝不调用付费 LLM。

Docker `HEALTHCHECK` 使用 `/healthz`，避免外部 Provider 故障引发容器重启风暴。编排平台是否接收流量应使用 `/readyz`。

### 5.2 安全默认值

- 非容器运行默认绑定 `127.0.0.1`。
- Compose 即使让容器监听 `0.0.0.0`，宿主机端口也只映射到 `127.0.0.1`。
- Origin allowlist 默认拒绝未知 Origin。
- 镜像以非 root UID/GID 运行。
- 构建上下文不得包含 `.env`、`data/`、`logs/`、`.git/`、`.venv/` 或任何密钥。
- API Key 只能在 `docker run`/Compose 运行时注入，不得使用 Dockerfile `ARG`/`ENV` 写入真实值。
- HTTP 响应和健康检查不得回显密钥、完整环境变量或敏感配置。

## 6. 容器镜像设计

### 6.1 Dockerfile

- 使用 Docker Official Python 3.11 slim 基础镜像。
- 使用 multi-stage build：builder 安装锁定依赖，runtime 只复制运行必需文件。
- 使用 `uv sync --locked` 或等价的锁文件严格安装，不在构建时重新解析依赖。
- 最终镜像不包含测试缓存、Git 历史、本地数据库和开发密钥。
- 创建固定非 root 用户，并确保 `/app/data`、`/app/logs` 可写。
- 使用 exec-form `ENTRYPOINT`/`CMD`，保证 SIGTERM 正确传递。
- 基础镜像至少固定到 Python minor + slim 发行版；是否 pin digest 由 CI 更新策略决定。

### 6.2 Compose

`compose.yaml` 只编排 RAG MCP Server，不自动下载大模型。它负责：

- runtime 环境变量；
- `data`、`logs` 挂载；
- `host.docker.internal`/host gateway；
- 本机端口限制；
- healthcheck；
- restart policy。

不得提交包含真实 Key 的 `.env`。可以提供 `.env.example`，其中只列变量名和安全占位符。

## 7. 阶段 J 任务拆分

### J0：v0.2 规格与范围冻结

- **状态**：本文件合入后完成。
- **修改文件**：`DEV_SPEC_V0.2.md`、`DEV_SPEC.md`、`README.md`。
- **验收标准**：目标、非目标、seam、安全门和后续决策均明确；GitHub Milestone/Issues 与本文件一致。

### J1：运行时配置与兼容入口

- **目标**：引入 `RuntimeOptions` 和 transport 选择，保持无参数启动仍为 stdio。
- **预计文件**：
  - `src/core/settings.py`
  - `src/mcp_server/runtime.py`
  - `src/mcp_server/server.py`
  - `main.py`
  - `pyproject.toml`
  - `config/settings.yaml`
  - `tests/unit/test_server_runtime.py`
- **测试方法**：
  - 配置优先级参数化测试；
  - 非法 transport、端口、path、origin 明确失败；
  - 原有 stdio initialize/tools 测试不变。
- **验收标准**：
  - 现有 MCP 客户端配置无需修改；
  - `--transport stdio` 与默认行为等价；
  - 安装后的 `mcp-server` console entrypoint 启动真实 Server；
  - 根 `main.py` 不再打印占位信息或污染 stdio stdout。

### J2：Streamable HTTP Adapter 与健康检查

- **目标**：通过同一个 `create_mcp_server()` 暴露 `/mcp`，增加 `/healthz`、`/readyz`。
- **预计文件**：
  - `src/mcp_server/http_app.py`
  - `src/mcp_server/runtime.py`
  - `tests/integration/test_mcp_http.py`
  - `tests/unit/test_health_endpoints.py`
- **测试方法**：ASGI 测试客户端 + 官方 MCP Streamable HTTP client。
- **验收标准**：
  - HTTP 与 stdio 的 tools 集合完全一致；
  - 官方客户端能 initialize、list tools、调用三个 tools；
  - `/healthz` 不访问外部 Provider；
  - `/readyz` 在 Ollama 不可达时返回 503 和脱敏状态；
  - 未允许 Origin 返回 403。

### J3：可复现 Docker 镜像

- **目标**：构建最小、非 root、无密钥的运行镜像。
- **预计文件**：
  - `Dockerfile`
  - `.dockerignore`
  - `.env.example`
  - `tests/container/test_image_contract.py`
- **测试方法**：`docker build`、镜像元数据检查、容器内 import/config smoke。
- **验收标准**：
  - 锁文件安装成功；
  - 最终用户 UID 不为 0；
  - 镜像中不存在 `.git`、`.env`、本地 `data`/`logs`；
  - 不提供密钥时构建仍成功；
  - `docker run --rm <image> --help` 返回 0。

### J4：Compose、持久化与 Ollama 连通

- **目标**：提供 Windows Docker Desktop 与 Linux Engine 都可理解的单节点运行配置。
- **预计文件**：
  - `compose.yaml`
  - `config/settings.container.yaml`（仅在无法通过安全运行时覆盖复用默认配置时新增）
  - `scripts/verify_container_runtime.py`
  - `tests/container/test_persistence.py`
- **测试方法**：容器启动、Ollama tags/embedding 连通、重启后数据查询。
- **验收标准**：
  - 容器可访问外部 `nomic-embed-text`；
  - 强制摄取后 Chroma/BM25 写入挂载目录；
  - 删除并重建容器后同一 collection 仍可查询；
  - API Key 只在运行时存在；
  - 宿主机监听地址默认为 `127.0.0.1`。

### J5：双 Transport E2E 与回归门禁

- **目标**：同一 fixture 分别通过 stdio 与 Streamable HTTP 返回等价 citations。
- **预计文件**：
  - `tests/e2e/test_mcp_http_client.py`
  - `tests/e2e/test_container_mcp.py`
  - `pyproject.toml`
- **测试方法**：官方 MCP ClientSession、隔离 Chroma、deterministic embedding、容器 stdio/HTTP round-trip。
- **验收标准**：
  - 两个 transport 均发现三个 tools；
  - `query_knowledge_hub` 的 citation source/collection 一致；
  - 测试不读取生产 `data/`，不访问付费 LLM；
  - Docker 用例标记为 `container`，默认离线门禁可在无 daemon 环境运行。

### J6：CI 与供应链基线

- **目标**：GitHub Actions 自动运行离线门禁和镜像构建，不依赖仓库 Secrets。
- **预计文件**：
  - `.github/workflows/ci.yml`
  - `.github/dependabot.yml`（如采用）
- **测试方法**：PR/Push workflow。
- **验收标准**：
  - `uv lock --check`、Ruff、mypy、离线 pytest 全通过；
  - Docker BuildKit 构建成功；
  - workflow 不运行 `external`/`llm` 测试；
  - workflow 不打印环境秘密；
  - 基础镜像与 Python 依赖具备可审计更新路径。

### J7：文档、演示与阶段收口

- **目标**：让新用户仅依赖 README 即可完成本地容器启动与 MCP HTTP 验证。
- **预计文件**：
  - `README.md`
  - `DEV_SPEC_V0.2.md`
  - `scripts/verify_container_runtime.py`
- **验收标准**：
  - 文档覆盖 Docker Desktop、Linux host gateway、数据备份/清理、密钥注入和常见故障；
  - 记录镜像构建、启动、健康、摄取、查询、重启持久化的真实耗时与 Trace；
  - 全部门禁通过并同步 GitHub；
  - 完成后停下供用户学习和验收，再决定公开云阶段。

## 8. 测试与质量门禁

### 8.1 默认离线门禁

```powershell
uv lock --check
python -m ruff check src tests scripts
python -m mypy src/mcp_server src/core/settings.py
python -m pytest -m "not llm and not external and not container"
```

默认门禁不得要求 Docker daemon、Ollama、网络、真实密钥或生产数据。

### 8.2 容器门禁

```powershell
docker build --pull -t rag-mcp:v0.2 .
python -m pytest -m container
docker compose config
python scripts/verify_container_runtime.py
```

真实 DeepSeek 摄取仍然是显式 external 验收，不进入 CI。

### 8.3 阶段完成总验收

按顺序验证：

1. stdio 回归；
2. Streamable HTTP 隔离 E2E；
3. Docker image contract；
4. 容器访问外部 Ollama；
5. 示例 PDF 真实摄取；
6. MCP HTTP 返回 citation；
7. 容器删除/重建后数据仍存在；
8. Trace 可读取且不含密钥；
9. CI 全绿；
10. 本地 `HEAD == origin/main`。

## 9. 风险、回退与决策门

| 风险 | 缓解 | 回退 |
|---|---|---|
| HTTP Adapter 破坏 stdio | 同一 Server Module、双 transport contract tests | 默认继续使用 stdio |
| 容器无法访问 Ollama | readiness、可配置 base URL、host gateway 文档 | 在宿主机运行现有 Server |
| Chroma 文件锁/并发损坏 | v0.2 限制单实例、显式 close、重启测试 | 停止容器后恢复 volume 备份 |
| 镜像泄露本地数据或密钥 | `.dockerignore`、非 root、image contract test | 阻止推送/发布镜像 |
| PDF 依赖在 slim 镜像缺失 | 构建阶段 import + fixture loader smoke | 固定系统包并记录原因 |
| SDK 升级造成协议变化 | `uv.lock`、双 transport E2E、版本上限 | 回退 lockfile/commit |

进入公开云部署前必须再次获得用户确认，并明确：

- 云平台与区域；
- 身份提供方和 OAuth/OIDC 方案；
- TLS、域名和 Origin allowlist；
- 数据备份、保留期限和删除策略；
- 费用上限；
- 单实例还是共享存储迁移。

## 10. 进度表

| 任务 | 状态 | 完成日期 | 备注 |
|---|---|---|---|
| J0 v0.2 规格与范围冻结 | [x] | 2026-08-20 | 目标、seam、安全门和验收任务已确定 |
| J1 运行时配置与兼容入口 | [ ] | — | |
| J2 Streamable HTTP 与健康检查 | [ ] | — | |
| J3 可复现 Docker 镜像 | [ ] | — | |
| J4 Compose、持久化与 Ollama | [ ] | — | |
| J5 双 Transport E2E | [ ] | — | |
| J6 CI 与供应链基线 | [ ] | — | |
| J7 文档、演示与阶段收口 | [ ] | — | |

## 11. 官方依据

- [MCP Python SDK：Running Your Server](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md)：stdio 用于本地子进程，部署使用 Streamable HTTP，SSE 已被取代。
- [MCP Streamable HTTP Specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx)：单一 MCP endpoint、Origin 校验和鉴权要求。
- [Docker Build Best Practices](https://docs.docker.com/build/building/best-practices/)：multi-stage、`.dockerignore`、小型可信基础镜像、CI 构建和版本固定。
- [Docker Build Secrets](https://docs.docker.com/build/building/secrets/)：真实密钥不得通过 Dockerfile `ARG`/`ENV` 写入镜像。
- [Dockerfile Reference](https://docs.docker.com/reference/dockerfile/)：`USER`、exec-form 启动和 `HEALTHCHECK` 行为。
