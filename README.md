# cr-agent · 多 Agent 代码审查协作平台

[![tests](https://github.com/tianhua/cr-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/tianhua/cr-agent/actions/workflows/ci.yml)
![coverage](https://img.shields.io/badge/coverage-91%25-brightgreen)
![python](https://img.shields.io/badge/python-3.11+-blue)

**cr-agent** 是一个基于 LangGraph Supervisor-Worker 架构的多 Agent 代码审查系统。你提交一段代码（本地文件或 GitHub PR），Supervisor 自动拆解审查任务，4 个专业 Worker Agent **并行**审查，最后聚合出一份结构化 Markdown 报告。

---

## 快速上手

```bash
# 安装依赖
pip install -r backend/requirements.txt

# 审查一个文件
python -m backend.cli review --file samples/sample_bad_python.py

# 审查 GitHub PR
python -m backend.cli review --pr https://github.com/octocat/Hello-World/pull/1

# 启动 API 服务
uvicorn backend.main:app --reload

# 跑全部测试
pytest backend/tests/ -v
```

## 架构

```
输入 (代码 + 语言)
     │
     ▼
┌───────────────────┐
│  decompose_node    │  ← LLM 分析代码 → 拆子任务
│  (Supervisor)      │
└──────┬────────────┘
       │  LangGraph fan-out（异步并行）
       ▼
┌──────┴───────────────────────────────┐
│  QualityWorker    SecurityWorker      │
│  PerformanceWorker  StructureWorker   │
│   ← 4 个 Worker 并行调 LLM 审查       │
└──────┬───────────────────────────────┘
       │  LangGraph fan-in（自动 barrier）
       ▼
┌───────────────┐
│ aggregate_node │  ← 去重 + 排序 → Markdown 报告
└───────┬───────┘
        ▼
      CLI / API / MCP 输出
```

### 核心设计

| 模块 | 职责 | 关键文件 |
|------|------|---------|
| **Supervisor** (`decompose_node`) | 分析代码 → 拆解子任务列表 (LLM → JSON) | `services/supervisor/decompose.py` |
| **Worker × 4** | 并行审查各维度；BaseWorker 模板方法模式 | `services/workers/{quality,security,performance,structure}.py` |
| **Aggregator** | 合并去重 + 排序 → 渲染 Markdown 报告 | `services/aggregator/{merge,report}.py` |
| **API** | `POST /api/v1/reviews` + `GET /reviews/{id}` | `api/reviews.py` |
| **CLI** | `--file <path>` 或 `--pr <url>` 两入口 | `cli/main.py` |
| **MCP Gateway** | FastMCP Server（5 个 Tool + 2 个 Resource） | `mcp/server.py` |
| **GitHub 集成** | `.patch` 拉取 + Webhook 验签 | `integrations/github.py` |

## 技术栈

| 层 | 技术 |
|----|------|
| 编排框架 | LangGraph (StateGraph + fan-out/fan-in) |
| Agent 基类 | 模板方法模式 + `__init_subclass__` 编译期校验 |
| 后端 | FastAPI async + SQLAlchemy async + SQLite |
| LLM | OpenAI 兼容 API（统一模型调用） |
| MCP | FastMCP + Streamable HTTP |
| 测试 | pytest + pytest-asyncio (106 tests, 91% coverage) |
| 质量 | ruff + mypy + pre-commit |
| 容器 | Docker + Compose |

## 评测结果

在 26 条人工标注样本上，LLM-as-Judge 三维度评分 + 硬指标 PRF 双轨评估：

| 分类 | composite | recall (PRF) |
|------|-----------|-------------|
| **安全审查** | 0.97 | 0.82 |
| **代码质量** | 0.90 | 0.75 |
| **性能** | 0.85 | 0.74 |
| **架构** | 0.75 | 0.67 |
| **综合** | **0.87** | **0.77** |

> recall 0.77（漏报少）但 precision 0.08（过报多）→ 下一步加置信度阈值过滤。

## 容错设计

- **LLM JSON 解析失败** → 降级为默认拆解 / info 级 finding
- **Worker 超时** (asyncio.wait_for 120s) → 返回降级标记，不阻塞
- **Worker 异常** → 捕获记录 error，其他 Worker 不受影响
- **死循环熔断** (max_iterations=3) → 直达 aggregate
- **空代码** → 直接返回 error，不调 LLM

## 设计决策

1. **自研 Supervisor-Worker → 不用 CrewAI**：每个节点自己能讲清，面试不甩锅给框架
2. **LangGraph fan-out/fan-in**：原生并行 + `operator.add` reducer 无竞态
3. **BaseWorker 模板方法**：4 个子类只设 system_prompt，核心流程复用
4. **MCP Gateway**：统一入口，外部客户端不关心内部图结构
5. **软硬双指标评测**：LLM-as-Judge + PRF（确定性可复现）

## 为什么做这个项目

这个项目是我的第二个秋招项目。第一个项目 [ai-resume-analyzer](https://github.com/tianhua/ai-resume-analyzer) 做了 RAG 全链路 + Agentic RAG + MCP，底层扎实但缺 **多 Agent 编排 / Agent 评测**。cr-agent 用实战补齐这些 R0 知识点：

- 🏗️ **多 Agent 编排**：LangGraph 状态图 + 并行分发 + 条件路由
- 🤖 **Agent 容错**：超时 / 异常 / 熔断 / 降级
- 📊 **Agent 评测**：LLM-as-Judge + 硬指标 PRF + Token 成本计量
- 💰 **成本控制**：TokenMeter 拦截计量 + 估算

## License

MIT
