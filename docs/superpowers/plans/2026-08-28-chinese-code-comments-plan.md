# 核心源码中文注释实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变任何原有代码的前提下，为后端核心源码和前端非测试源码添加中文教学注释。

**Architecture:** 只插入语言原生注释，不新增 docstring，不调整 import、空白或代码顺序。每个文件包含职责、依赖、关键机制和工作流位置；核心编排文件额外包含简短流程图。

**Tech Stack:** Python、FastAPI、LangGraph、Pydantic、Vue 3、TypeScript、SSE

**Spec:** `docs/superpowers/specs/2026-08-28-chinese-code-comments-design.md`

## Global Constraints

- 只允许新增 `#`、`//`、`/* */` 或 `<!-- -->` 注释。
- 不修改、删除或移动任何已有代码字符和代码行。
- 不处理 `backend/tests`、`backend/evals` 和前端 `*.test.ts`。
- 注释必须使用中文，并解释设计原因，不逐行翻译显然代码。
- 不读取或复制 `.env` 中的密钥。

---

### Task 1: 后端入口、API 与运行时

**Files:**
- Modify: `backend/src/deep_research/{__init__.py,config.py,llm.py,runtime.py}`
- Modify: `backend/src/deep_research/api/{__init__.py,main.py,routes.py,schemas.py}`
- Modify: `backend/src/deep_research/services/runtime.py`

- [ ] 在每个文件顶部插入职责、依赖和工作流位置说明。
- [ ] 在 API、SSE、后台任务、结构化输出修复、恢复与取消等关键位置插入就近解释。
- [ ] 运行 `python -m ruff check src`，预期通过。

### Task 2: Graph、State 与 Agent 节点

**Files:**
- Modify: `backend/src/deep_research/graph/*.py`
- Modify: `backend/src/deep_research/state/*.py`
- Modify: `backend/src/deep_research/nodes/*.py`

- [ ] 为 Graph 构建、条件路由、State reducer 和 state patch 添加中文解释。
- [ ] 为 Clarifier、Planner、Supervisor、Researcher、Gap Analyzer、Writer、Reviewer、Finalizer 标明输入、输出和边界。
- [ ] 在 `graph/builder.py` 顶部加入主工作流 ASCII 图。
- [ ] 运行 `python -m ruff check src`，预期通过。

### Task 3: 领域模型与横切服务

**Files:**
- Modify: `backend/src/deep_research/domain/*.py`
- Modify: `backend/src/deep_research/services/*.py`（Task 1 已处理的 runtime 除外）
- Modify: `backend/src/deep_research/persistence/*.py`
- Modify: `backend/src/deep_research/security/*.py`
- Modify: `backend/src/deep_research/tools/*.py`
- Modify: `backend/src/deep_research/prompts/*.py`

- [ ] 解释 Pydantic 约束、Source/Evidence 关系、事件信封、引用渲染和预算等关键概念。
- [ ] 解释 SQLite checkpoint、运行元数据、URL 安全、脱敏、搜索适配和重试边界。
- [ ] 运行后端测试和 Ruff，记录与注释无关的既有失败。

### Task 4: 前端非测试源码

**Files:**
- Modify: `frontend/src/{main.ts,App.vue}`
- Modify: `frontend/src/api/research.ts`
- Modify: `frontend/src/stores/research.ts`
- Modify: `frontend/src/types/research.ts`
- Modify: `frontend/src/components/*.vue`

- [ ] 用 TypeScript、Vue 和 HTML 原生注释解释入口、类型、SSE 客户端、状态投影和组件职责。
- [ ] 在 Store 和 API 客户端标明“后端事件 -> 状态投影 -> UI”的数据流。
- [ ] 运行前端测试和生产构建，预期通过。

### Task 5: 只注释差异审计

**Files:**
- Review: `backend/src/deep_research/**`
- Review: `frontend/src/**`（排除测试文件）

- [ ] 检查每个范围内文件都有中文文件级说明。
- [ ] 使用 Git 差异脚本验证新增行仅为注释或注释块内容，且没有删除行。
- [ ] 复核用户原有未提交改动仍然保留。
- [ ] 汇总文件数量、验证结果和任何既有失败，不创建 Git 提交。
