# DataWhisperer

DataWhisperer 是一个面向业务人员的自然语言数据分析智能体。用户可以用中文提出数据问题，系统自动读取 MySQL 示例库结构，生成安全 SQL，执行查询，并返回表格、图表和业务分析结论。

当前项目已经更新到 **V3.11.2：真实对话会话管理版本**。

版本入口：

- `v1.0.0`：Text-to-SQL MVP，跑通自然语言查数、SQL 安全校验、查询执行、图表和分析结论。
- `v2.0.0`：引入 PromptOps、SQL 自动修复和基础评测集，使系统具备更强的可治理、可追踪和可评测能力。
- `v3.0.0`：引入本地指标口径库和轻量检索，将 GMV、销售额、客单价、订单数、复购率等业务定义注入 SQL 生成 prompt。
- `v3.1.0`：升级为混合指标检索，结合关键词/别名命中和轻量 n-gram 相似度。
- `v3.2.0`：新增指标检索评测集，验证问题是否命中正确业务指标。
- `v3.3.0`：接入 Milvus 向量数据库作为指标检索层，并保留本地检索自动兜底。
- `v3.4.0`：将指标向量化升级为 DashScope `text-embedding-v4`，Milvus 索引使用真实语义向量。
- `v3.5.0`：升级中文控制台，新增数据结构资料和 RAG 知识库资料的上传、列表、预览、删除能力。
- `v3.6.0`：增强分析体验，加入可展开时间线、结论逐字输出、图表交互、统一动效和追问建议。
- `v3.6.1`：优化 AI 查数页面，分析结论限制在卡片内部滚动，分析过程默认收起，并移除重复的轨迹页签。
- `v3.6.2`：继续优化 AI 查数页面，分析结论卡片随内容自然撑开，收起的分析过程展示实时进度摘要。
- `v3.6.3`：优化分析结论阅读区样式，追问建议默认折叠，避免干扰主分析结果。
- `v3.6.4`：修复右侧结果卡片在 flex 布局中被压缩的问题，避免分析结论、告警和分析过程互相覆盖。
- `v3.6.5`：升级 SQL Viewer，提供浅色代码区、行号、基础语法高亮、格式化、下载和复制操作。
- `v3.6.6`：优化数据结构和 RAG 知识库资料管理页，升级上传区、空状态、文件列表和预览区视觉体验。
- `v3.7.0`：新增评测中心，前端展示 Text-to-SQL、SQL 安全和指标检索评测结果，支持一键运行、KPI、版本对比和用例明细。
- `v3.7.1`：吸收专业模型评测页面设计，将评测中心升级为页签式工作台，新增质量趋势、问题分布、最近任务、模型对比和错误案例视图。
- `v3.7.2`：新增独立测试集管理页面和评测测试集上传接口，支持上传、列表、预览和删除自定义离线评测文件。
- `v3.8.0`：增强 AI 查数结果区，新增图表、表格和 SQL 的导出能力，方便复制到报告、PPT、Word 和 Typora。
- `v3.8.1`：升级 SQL 审阅体验，展示原始问题、生成说明和校验结果，帮助 SQL 人员理解自然语言到 SQL 的转换逻辑。
- `v3.8.2`：修复图表容器渲染尺寸问题，提升图表在不同结果区布局下的稳定性。
- `v3.8.3`：SQL 代码块增加中文标准注释，解释查询维度、数据来源、关联条件、分组、排序和 LIMIT 等关键语句。
- `v3.8.4`：主图表恢复 Canvas 展示，保留外部导出按钮，并避免图表内部工具栏和缩放条干扰阅读。
- `v3.8.5`：修复图表 tooltip 被全屏撑大的问题，悬停提示恢复为轻量小浮层。
- `v3.8.6`：打通测试集管理和评测中心，上传的测试集可以在评测中心选择并运行 Text-to-SQL 回归评测。
- `v3.8.7`：优化评测中心的数据源选择器，并新增 100 条可上传的 Text-to-SQL 回归测试集样例。
- `v3.8.8`：修复评测数据源菜单进入页面后默认展开的问题，并收敛下拉菜单尺寸和视觉层级。
- `v3.8.9`：移除评测数据源选择框后的重复数据集状态文字，让工具栏更干净。
- `v3.8.10`：固定评测数据源选择器宽度，避免切换不同测试集时工具栏左右抖动。
- `v3.9.0`：将 AI 查数升级为对话式数据分析工作台，支持欢迎卡片、底部输入框、Enter 发送和消息式结果卡片。
- `v3.9.1`：优化对话助手欢迎文案，示例问题点击后直接发送，减少用户首次体验路径。
- `v3.10.2`：参考专业对话式分析产品重构 AI 查数界面，新增场景卡片、最近对话、对话标题栏、当前条件和更精致的消息卡片视觉。
- `v3.10.3`：继续贴近真实聊天式数据助手，重做欢迎卡片、用户气泡、助手结果卡片、图表展示、详情/SQL 操作区和追问建议区。
- `v3.10.4`：优化对话结果细节，用户消息去掉顶部“你”标签并显示时间，详细数据和生成 SQL 改为结果卡片底部下拉展开，追问建议固定在回复最底部。
- `v3.10.5`：继续精简 AI 查数结果卡片，隐藏图表说明和本地演示 SQL 提示，详情按钮保持向下展开的视觉反馈。
- `v3.10.6`：精简生成 SQL 下拉内容，移除原始问题、生成说明和校验结果三栏，只保留可复制、可下载的 SQL 代码。
- `v3.10.7`：优化 AI 查数等待体验，将生硬的长条文字提示改为轻量动态思考气泡，让用户明确感知系统正在分析数据。
- `v3.10.8`：压缩 AI 查数首屏欢迎卡尺寸，弱化大卡片展示感，让入口更像真实对话产品。
- `v3.10.9`：统一 AI 查数欢迎消息和分析结果消息的最大宽度，避免对话前后忽短忽长。
- `v3.10.10`：支持 AI 查数多轮对话历史保留，新问题不会覆盖上一轮结果，旧图表会归档为静态快照。
- `v3.10.11`：统一 AI 查数消息流和底部输入框的内容列宽，让对话区域与输入区域左右边界对齐。
- `v3.10.12`：新增系统设置页面，集中展示数据源配置、模型配置、账户偏好和安全策略，并支持本地草稿保存与连接检测。
- `v3.11.0`：在数据结构模块新增 3D 数据关系图谱，自动读取本地数据库表、主键、外键和字段信息，点击节点查看表详情。
- `v3.11.1`：修复 3D 图谱刷新时旧标签清理异常的问题，并收敛表详情面板的横向溢出。
- `v3.11.2`：优化 AI 查数最近对话逻辑，新建对话会生成真实会话项，发送问题后自动更新标题和轮次，左侧不再展示写死的假对话。

项目第一阶段重点不是堆概念，而是先做出一个能真实跑通的 Text-to-SQL 数据分析闭环。V2 补充大模型工程化能力，V3 开始加入 RAG 业务知识增强，后续会继续扩展 MCP 工具化和多智能体协作。

## 项目亮点

- 自然语言转 MySQL `SELECT` 查询。
- 自动读取数据库表、字段、主键、外键信息。
- 服务端 SQL 安全校验，禁止写入、删除、DDL、多语句和危险函数。
- 自动补充 `LIMIT`，避免一次性返回过多数据。
- 返回查询表格、ECharts 图表配置、业务分析结论和执行轨迹。
- 提供中文 Web 控制台，便于演示和面试讲解。
- LLM 使用 OpenAI-compatible 封装，默认适配 DashScope/Qwen，也可以切换 OpenAI、DeepSeek 等兼容服务。
- 没有配置大模型 API Key 时，部分典型问题会走演示兜底规则，方便本地快速验证。
- V2 引入 PromptOps，将 SQL 生成、SQL 修复、分析总结、图表推荐 prompt 拆成版本化模板。
- SQL 校验失败或数据库执行失败时，系统最多自动修复 1 次，并记录 `repair_count`。
- 内置基础 Text-to-SQL 评测集，可快速检查 SQL 安全、关键 SQL 片段和图表推荐是否退化。
- V3 引入本地指标口径库，支持 GMV、销售额、客单价、订单数、复购率等业务指标检索。
- SQL 生成和 SQL 修复 prompt 会注入检索到的指标口径，让模型按业务定义生成 SQL。
- API 返回 `retrieved_metrics`，方便追踪本次问题参考了哪些业务指标定义。
- V3.1 使用混合检索策略：关键词/别名精确匹配 + 本地 n-gram 语义相似度。
- V3.2 增加指标检索评测集，检查指标召回是否正确、是否误召回禁止指标。
- V3.3 增加 Milvus 向量数据库检索层，指标 Markdown 仍作为知识源，Milvus 作为可重建索引。
- Milvus 未启动、未安装客户端或索引未同步时，系统可自动回退到本地 hybrid 检索，避免演示环境阻塞。
- V3.4 使用 DashScope `text-embedding-v4` 生成指标向量，hashing 向量化器保留为本地兜底。
- V3.5 将控制台拆成 AI 查数、数据结构、RAG 知识库三个工作区。
- 支持数据结构资料和 RAG 知识库资料上传、列表查看、文本预览和删除。
- V3.6 将执行步骤升级为可展开分析时间线，展示从理解问题到生成结论的完整过程。
- V3.6 支持分析结论逐字输出、图表缩放/保存/点击反馈和自动追问建议。
- V3.6.1 优化 AI 查数页面的信息密度，减少重复轨迹展示，让业务结论和分析过程更适合演示场景。
- V3.6.2 让分析结论区域按内容自适应高度，并在分析过程收起时保留“正在处理/已完成”的状态感知。
- V3.6.3 将追问建议改为默认折叠入口，并优化分析结论正文的内边距、背景和阅读层次。
- V3.6.4 让结果区卡片保持内容自适应高度，滚动交给结果区容器处理，避免长结论覆盖后续模块。
- V3.6.5 将 SQL 展示从黑色终端块升级为浅色只读代码查看器，便于面试演示、调试和截图传播。
- V3.6.6 让资料上传和文件管理界面更接近企业级控制台，支持拖拽上传、结构化空状态和浅色文件预览。
- V3.7 新增 Evaluation Center 评测中心，把模型效果从“能演示”升级为“可度量、可追踪、可对比”。
- 评测中心覆盖 Text-to-SQL 生成质量、SQL 安全边界和 RAG/指标口径检索命中率。
- V3.7.1 将评测页升级为专业工作台，支持质量趋势、问题分布、最近评测任务、模型策略对比、错误案例和可展开用例明细。
- V3.7.2 新增独立测试集管理页面，支持上传、查看、预览和删除自定义评测测试集，评测中心保持专注展示评测结果。
- V3.8 强化结果资产化能力，图表可以复制 PNG、下载 SVG，表格可以复制为 Word 友好的 HTML、Markdown 或 CSV。
- V3.8 SQL 页面从单纯代码展示升级为 SQL 审阅区，包含自然语言问题、生成说明、只读校验、语法结构校验、执行验证和书写规范提示。
- V3.8.3 在 SQL 代码内部生成中文注释，方便 SQL 人员审阅，也方便面试时解释模型生成 SQL 的逻辑。
- V3.8.4-V3.8.5 进一步优化图表展示，主图表保持 Canvas 视觉效果，同时修复 tooltip 样式冲突。
- V3.8.6 将测试集管理接入评测中心，用户上传 JSON、JSONL、CSV、TXT 或 YAML 测试集后，可以直接选择该文件运行自定义 Text-to-SQL 评测。
- V3.8.7 将评测数据源从系统原生下拉框升级为自定义选择器，并提供 `evals/text_to_sql_upload_100_cases.jsonl` 作为 100 条上传评测样例。
- V3.8.8 明确处理自定义下拉框的隐藏状态，避免进入评测中心时菜单常驻展开，同时让选择器更轻量、紧凑。
- V3.8.9 精简评测中心顶部工具栏，数据集名称只保留在选择框内部，避免右侧重复状态文字干扰阅读。
- V3.8.10 固定评测数据源选择器布局，长文件名在按钮内部省略，不再撑开工具栏。
- V3.9.0 将 AI 查数从表单式控制台升级为对话式体验，用户可以像聊天一样提问，结果以助手消息卡片展示结论、图表、表格、SQL、分析过程和追问建议。
- V3.9.1 进一步降低首次使用门槛，用户点击欢迎卡片里的推荐问题即可自动发起分析，并将助手开场白改得更轻量、直接。
- V3.10.2 将 AI 查数页面继续产品化，加入最近对话、场景化快捷入口、当前生效条件、用户/助手头像和更轻量的聊天式布局，让首次打开页面更像一个真实数据助手产品。
- V3.10.3 进一步收敛 dashboard 感，AI 查数结果改成一条完整助手回复：先给结论，再展示轻量图表，底部收纳详细数据、生成 SQL 和追问建议，更适合演示和真实使用。
- V3.10.4 将结果详情交互继续贴近聊天产品：表格和 SQL 不再作为顶部标签页抢占注意力，而是通过底部胶囊按钮下拉查看，主路径聚焦“结论 + 图表 + 追问”。
- V3.10.5 去掉结果卡片里的说明噪音，隐藏图表交互说明和演示 SQL 警告，让用户注意力集中在结论、图表、详情下拉和追问上。
- V3.10.6 继续降低 SQL 面板的信息密度，移除偏工程调试的 SQL 解释和校验卡片，让界面更像面向业务用户的数据助手。
- V3.10.7 将“正在分析”状态从结果卡片中拆出来，改成三个动态圆点和短提示文案，避免加载时出现大面积空白或突兀长条。
- V3.10.8 继续收敛首屏视觉重心，欢迎卡改成更窄、更轻、更紧凑的对话引导区，减少打开页面时的压迫感。
- V3.10.9 将欢迎卡、分析结果卡统一到同一条对话宽度线上，让用户提问前后的视觉节奏更稳定。
- V3.10.10 将上一轮对话在新问题开始前归档到历史区，解决“发一次消息旧内容就消失”的问题，更贴近真实聊天式数据助手。
- V3.10.11 将消息流和输入框收敛到统一的居中内容列，修复打开页面时上方对话区域与底部输入框不对齐的问题。
- V3.10.12 新增系统设置配置中心入口，将数据源、模型、账户和安全边界集中展示，先支持前端草稿保存和连通性检测，后续可平滑接入服务端加密配置接口。
- V3.11.0 将数据结构模块升级为“资料管理 + 3D 关系图谱”双视图，让用户可以通过三维节点网络直观看懂表之间的主外键关系，并点击节点查看表详情。
- V3.11.0 在数据结构模块新增 3D 数据关系图谱，将数据库 schema 从文件清单升级为可旋转、可缩放、可点击的关系网络；节点代表数据表，连线代表外键关系，右侧详情面板展示主键、核心字段、完整字段列表和关联关系。
- V3.11.1 修复刷新图谱时 `label.remove is not a function` 的旧标签清理问题，同时让右侧详情表格和关联关系在窄面板内自动换行或省略，避免出现突兀横向滚动。

## 技术栈

- 后端：FastAPI、Pydantic、SQLAlchemy
- 数据库：MySQL 8
- 向量数据库：Milvus standalone
- 大模型：OpenAI-compatible Chat Completions，默认 DashScope/Qwen
- Embedding：DashScope `text-embedding-v4`
- 前端：FastAPI StaticFiles、原生 HTML/CSS/JavaScript、ECharts
- 测试：pytest、ruff
- 部署辅助：Docker Compose

## 架构概览

```mermaid
flowchart TD
    U["用户中文问题"] --> API["FastAPI: POST /api/chat/query"]
    API --> O["DataAnalysisOrchestrator"]
    O --> S["Schema Tool: 读取表结构"]
    O --> M["Metric Retriever: 检索业务指标口径"]
    M --> VDB["Milvus: 指标向量索引"]
    M --> LOCAL["Local Hybrid: 本地兜底检索"]
    O --> P["PromptRegistry: 读取版本化提示词"]
    O --> SQL["SQL Tool: 生成并校验 SQL"]
    O --> RPAIR["SQL Repair: 失败后自动修复"]
    O --> Q["Query Tool: 执行只读查询"]
    O --> C["Chart Tool: 推荐图表"]
    O --> I["Insight Tool: 生成业务结论"]
    S --> R["统一响应"]
    M --> SQL
    P --> SQL
    SQL --> R
    RPAIR --> R
    Q --> R
    C --> R
    I --> R
    R --> UI["中文 Web 控制台 / API 调用方"]
```

核心设计思想：

- API 层保持轻量，只负责请求、响应和异常转换。
- Orchestrator 负责编排完整 Agent 流程。
- Tools 负责具体能力，后续可以平滑升级成 MCP 工具。
- Prompt 不是安全边界，SQL 安全必须由服务端代码兜底。
- 返回 `trace_steps`，方便调试和向面试官解释每一步发生了什么。
- 返回 `prompt_versions` 和 `repair_count`，用于追踪本次请求使用的提示词版本和 SQL 修复次数。
- 返回 `retrieved_metrics`，用于追踪本次请求检索到的业务指标口径。

## 目录结构

```text
app/
  api/          FastAPI 路由
  agent/        Agent 主控编排流程
  core/         配置、数据库、大模型客户端
  evals/        Text-to-SQL 评测 runner
  models/       Pydantic 请求/响应模型
  rag/          指标口径检索、向量化、Milvus 同步工具
  tools/        Schema、SQL、查询、图表、分析工具
docs/
  architecture.md       架构说明
  interview-guide.md    面试讲解稿
  v1-release-notes.md   v1 发布说明
  v2-promptops-design.md V2 PromptOps 设计说明
  v3-rag-metrics-design.md V3 RAG 指标口径库设计说明
evals/
  text_to_sql_cases.json 基础 Text-to-SQL 评测集
  metric_retrieval_cases.json 指标检索评测集
knowledge/
  metrics/              GMV、销售额、客单价、订单数、复购率等指标口径
prompts/
  sql_generation/       SQL 生成提示词模板
  sql_repair/           SQL 修复提示词模板
  insight_summary/      分析总结提示词模板
  chart_recommendation/ 图表推荐提示词模板
scripts/
  mysql_sample.sql      示例电商销售数据库
static/
  index.html            中文控制台页面
storage/
  schema_files/          数据结构资料上传目录，已加入 .gitignore
  rag_knowledge/         RAG 知识库资料上传目录，已加入 .gitignore
tests/
  单元测试和接口契约测试
```

## 快速启动

### 1. 创建 Python 环境

```powershell
cd F:\Al_development\DataWhisperer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

如果 PowerShell 对 `.[dev]` 解析有问题，可以改用：

```powershell
pip install -r requirements-dev.txt
```

### 2. 配置环境变量

```powershell
copy .env.example .env
notepad .env
```

DashScope/Qwen 示例配置：

```env
DASHSCOPE_API_KEY=你的 DashScope API Key
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
DASHSCOPE_EMBEDDING_DIMENSION=1024
```

说明：

- `.env.example` 是模板文件，可以提交到 GitHub。
- `.env` 是本地真实配置文件，已经加入 `.gitignore`。
- 不要把真实 API Key 提交到 GitHub。
- V3.4 后聊天模型和 embedding 默认都可以复用 `DASHSCOPE_API_KEY`。

### 3. 启动 MySQL 示例库

推荐使用：

```powershell
docker-compose up -d mysql
```

部分环境也可以使用：

```powershell
docker compose up -d mysql
```

第一次启动时，MySQL 会自动执行：

```text
scripts/mysql_sample.sql
```

示例数据会写入：

```text
volumes/mysql/
```

这个目录已经加入 `.gitignore`。

### 4. 可选：启动 Milvus 指标向量库

默认情况下项目使用本地 hybrid 指标检索，可以直接运行。
如果想演示 V3.4 的 Milvus + DashScope Embedding 向量检索能力，可以启动 Milvus 并同步指标索引：

```powershell
pip install -e ".[milvus]"
docker-compose up -d etcd minio milvus
python -m app.rag.milvus_sync
```

然后在 `.env` 中切换检索提供方：

```env
METRIC_RETRIEVAL_PROVIDER=milvus
EMBEDDING_PROVIDER=dashscope
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
DASHSCOPE_EMBEDDING_DIMENSION=1024
MILVUS_URI=http://127.0.0.1:19530
MILVUS_METRIC_COLLECTION=datawhisperer_metrics
MILVUS_AUTO_FALLBACK=true
```

说明：

- `knowledge/metrics/*.md` 仍然是指标口径的唯一知识源。
- Milvus 只保存可重建的向量索引，不保存不可恢复的业务配置。
- V3.4 使用 `text-embedding-v4` 生成 1024 维指标向量，旧的 128 维 hashing 索引需要重新同步。
- `MILVUS_AUTO_FALLBACK=true` 时，Milvus 不可用会自动回退到本地检索。

### 5. 启动后端服务

```powershell
uvicorn app.main:app --reload --port 8081
```

访问地址：

- 控制台：http://127.0.0.1:8081/
- Swagger 文档：http://127.0.0.1:8081/docs
- 健康检查：http://127.0.0.1:8081/api/health
- 示例问题：http://127.0.0.1:8081/api/examples
- 数据结构：http://127.0.0.1:8081/api/schema/overview
- 数据结构资料文件：http://127.0.0.1:8081/api/files/schema
- RAG 知识库资料文件：http://127.0.0.1:8081/api/files/rag
- 运行内置评测：http://127.0.0.1:8081/api/evaluations/run
- 评测测试集文件：http://127.0.0.1:8081/api/evaluations/datasets

## 主要接口

### `GET /api/health`

用于检查服务是否正常启动。

### `GET /api/schema/overview`

读取当前 MySQL 示例库的表结构摘要，包括表名、字段、字段类型、主键和外键。

### `GET /api/examples`

返回内置演示问题，前端左侧的示例问题列表来自这个接口。

### `POST /api/chat/query`

自然语言查数主入口。

请求示例：

```json
{
  "question": "查询各地区订单数量",
  "max_rows": 100
}
```

响应字段：

- `generated_sql`：最终执行的安全 SQL。
- `sql_explanation`：SQL 的作用说明。
- `columns`：结果列名。
- `rows`：查询结果。
- `chart`：ECharts 图表配置。
- `insight`：业务分析结论。
- `warnings`：风险提示或兜底说明。
- `trace_steps`：Agent 执行轨迹。
- `prompt_versions`：本次请求使用过的 prompt 版本。
- `retrieved_metrics`：本次请求检索到的业务指标口径。
- `repair_count`：SQL 自动修复次数。

### 文件管理接口

V3.5 新增两组资料管理接口：

```text
GET    /api/files/schema
POST   /api/files/schema
GET    /api/files/schema/{file_id}/preview
DELETE /api/files/schema/{file_id}

GET    /api/files/rag
POST   /api/files/rag
GET    /api/files/rag/{file_id}/preview
DELETE /api/files/rag/{file_id}
```

当前文件上传用于资料管理和控制台展示。后续版本可以继续接入自动解析、CSV 入库、RAG 切片和 Milvus 索引同步。

### `POST /api/evaluations/run`

V3.7 新增评测中心接口，用于运行内置离线评测套件，不调用真实大模型，适合本地演示和回归检查。

当前内置套件：

- `text_to_sql`：验证典型业务问题是否生成符合规则的 SQL 和图表类型。
- `sql_safety`：验证服务端 SQL 安全边界是否能拦截 DROP、DELETE、多语句等风险。
- `metric_retrieval`：验证指标口径/RAG 检索是否命中正确业务定义。

接口返回 KPI、套件汇总、用例明细、版本质量快照、质量趋势、问题分布、最近任务和模型对比数据，前端“评测中心”页面会直接消费这个接口。

### 评测测试集管理接口

V3.7.2 新增测试集文件管理接口，用于上传自定义离线评测集。当前版本先完成文件管理和预览，后续可以将这些文件解析成真实评测用例并接入评测 runner。

```text
GET    /api/evaluations/datasets
POST   /api/evaluations/datasets
GET    /api/evaluations/datasets/{file_id}/preview
DELETE /api/evaluations/datasets/{file_id}
```

支持格式：`.json`、`.jsonl`、`.csv`、`.yaml`、`.yml`、`.txt`。推荐每条用例包含 `question`、`expected_sql_contains` 或 `expected_metrics` 等字段。

V3.8.6 起，评测中心可以选择测试集管理中上传的文件运行自定义 Text-to-SQL 回归评测。`POST /api/evaluations/run` 支持传入：

```json
{
  "dataset_file_id": "上传文件 id"
}
```

推荐测试集字段：

```json
{
  "id": "case_region_orders",
  "question": "查询各地区订单数量",
  "expected_sql_contains": ["orders", "regions", "COUNT"],
  "forbidden_sql_contains": ["DELETE", "DROP"],
  "expected_columns": ["region_name", "order_count"],
  "expected_chart_type": "bar",
  "tags": ["custom", "region"]
}
```

也支持 JSON 数组、JSONL、CSV 和 TXT。TXT 会按“一行一个问题”运行基础生成评测。

V3.8.7 新增可直接上传演示的 100 条 JSONL 样例：

```text
evals/text_to_sql_upload_100_cases.jsonl
```

这份样例覆盖最近 6 个月销售趋势、品类销售额占比、地区客单价、商品销售额下滑、地区订单数量、华东销量 Top 商品和行业客户数量等场景。可以在“测试集管理”页面上传，然后在“评测中心”的“评测数据源”中选择该文件运行。

## 示例问题

也可以通过 `GET /api/examples` 获取。

- 查询最近 6 个月每月销售额趋势
- 查询各商品品类销售额占比
- 哪个地区客单价最高
- 找出销售额下滑最明显的商品
- 查询华东地区销量前三的商品及其环比增长
- 查询各地区订单数量
- 统计每个行业的客户数量

## SQL 安全策略

DataWhisperer 第一阶段只允许只读分析查询。

服务端会拦截：

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `TRUNCATE`
- 多语句 SQL
- SQL 注释
- 导出文件类语句

同时会自动给没有 `LIMIT` 的查询补上行数限制。

这里体现了一个重要原则：

> 提示词不是安全边界，服务端代码才是安全边界。

## 测试

```powershell
pytest
ruff check .
```

当前测试覆盖：

- SQL 安全校验
- 图表推荐规则
- 示例问题接口
- API 路由契约
- PromptRegistry 提示词模板渲染
- SQL 自动修复链路
- Text-to-SQL 基础评测集
- RAG 指标口径检索
- 指标检索评测集
- V3.4 DashScope embedding 客户端和 hashing 本地兜底
- Milvus 指标检索命中与本地检索兜底
- Milvus 指标文档同步构造
- V3.5 文件上传、预览、删除和 API 路由契约
- V3.7 评测中心 API、Text-to-SQL 评测、SQL 安全评测和指标检索评测

运行基础评测：

```powershell
python -m app.evals.text_to_sql
```

运行指标检索评测：

```powershell
python -m app.evals.metric_retrieval
```

当前评测结果：

```text
total: 5
passed: 5
failed: 0
pass_rate: 1.0
```

## 面试讲法

可以用下面这段作为 1 分钟项目介绍：

> DataWhisperer 是我做的一个 Text-to-SQL 数据分析智能体。它面向没有 SQL 能力的业务用户，用户输入中文问题后，系统会读取 MySQL 表结构，并检索 GMV、客单价、复购率等业务指标口径，再调用大模型生成查询 SQL。服务端安全层只允许只读查询，SQL 失败时最多自动修复一次，最后返回表格、图表配置和业务分析结论。V2 引入 PromptOps 和 SQL 自修复，V3 引入 RAG 指标口径库，V3.4 使用 DashScope text-embedding-v4 和 Milvus 做语义检索，V3.5 将前端升级为三工作区控制台，V3.6 增强分析体验，V3.7 增加模型评测中心和模型策略对比，V3.8 增强结果导出、SQL 审阅和自定义测试集评测能力，使系统从“能跑通”升级为“可治理、可追踪、可评测、能理解业务指标、具备向量检索基础设施和产品化交互体验”的大模型工程项目。

更多讲解内容见：[docs/interview-guide.md](docs/interview-guide.md)。

## 常见问题

### 配了 API Key，但页面仍然提示用了演示兜底规则

先确认 Key 是否写到了 `.env`，而不是只写在 `.env.example`。

修改 `.env` 后需要重启服务。

### MySQL 容器启动后马上退出

如果日志里出现：

```text
--initialize specified but the data directory has files in it
```

说明 MySQL 第一次初始化失败后留下了半初始化数据。对于本项目 demo，可以删除：

```text
volumes/mysql/
```

然后重新启动：

```powershell
docker-compose up -d mysql
```

如果日志里出现：

```text
No space left on device
```

说明 Docker 原来的 named volume 空间不足。本项目已经改为使用 `./volumes/mysql` 绑定目录，通常可以避免这个问题。

### 8080 被旧服务占用

可以换端口启动：

```powershell
uvicorn app.main:app --reload --port 8081
```

当前推荐使用 8081。

### Milvus 没启动时还能运行吗

可以。默认 `METRIC_RETRIEVAL_PROVIDER=local`，系统会使用本地 hybrid 检索。

如果切到 `METRIC_RETRIEVAL_PROVIDER=milvus`，但 Milvus 没启动或指标索引没同步，只要
`MILVUS_AUTO_FALLBACK=true`，系统会自动回退到本地 hybrid 检索，保证核心查数流程不被阻塞。

## 后续路线

- V1：Text-to-SQL MVP，跑通自然语言查数闭环。
- V2：PromptOps 提示词治理、SQL 自动修复、基础 Text-to-SQL 评测集。
- V3：RAG 指标口径库，支持 GMV、客单价、复购率等业务定义检索和 prompt 注入。
- V3.1：混合指标检索，结合关键词/别名命中和轻量 n-gram 相似度。
- V3.2：指标检索评测集，验证指标召回、误召回和报告输出。
- V3.3：Milvus 向量数据库检索层，支持指标向量索引同步和本地检索兜底。
- V3.4：DashScope `text-embedding-v4` 指标向量化，Milvus 使用真实语义向量检索。
- V3.5：产品控制台升级，新增数据结构资料和 RAG 知识库资料管理页面。
- V3.6：分析体验增强，加入时间线、逐字输出、图表交互、统一动效和追问建议。
- V3.7：评测中心，支持 Text-to-SQL、SQL 安全和指标检索的可视化评测工作台。
- V3.8：结果导出和 SQL 审阅增强，支持图表/表格复制下载、SQL 校验说明、代码内中文注释和自定义测试集评测。
- V3.9：RAG 上传文件自动切片并同步 Milvus，数据结构上传文件接入 schema 解析。
- V4：MCP 工具化，把数据库查询、图表生成、导出能力包装成工具。
- V5：多智能体拆分，引入 Schema Analyst、SQL Engineer、Chart Designer、Report Writer。
- V6：评测体系增强，增加真实 LLM 评测、SQL 正确率、修复成功率和分析结论质量评估。
