# PRD: agent-team

**日期:** 2026-06-24
**状态:** Draft

## 1. 概述

### 1.1 问题陈述
多 Agent 协作场景中，各 Agent 无法感知彼此身份、无法直接通信、无法查询通讯录。需要一个轻量级的 Agent 间通信基础设施，基于 SQLite 持久化。

### 1.2 目标用户
- 运行中的 Agent 实例（通过内置 tool 调用通信能力）
- Agent 系统管理员（通过外部 API 管理 Agent 生命周期）

### 1.3 成功指标
- 完成 6 个内置 tool 的 TDD 实现并通过测试
- SQLite 持久化，重启后数据不丢失
- 消息投递延迟 < 10ms（本地 SQLite 写入）
- 代码架构清晰，模块边界明确

## 2. 功能需求

### 2.1 核心功能（MVP）

- [x] F1: Agent 注册与查询 — 创建、删除、查看 Agent 基本信息
- [x] F2: 通讯录 — 全局可见的 Agent 列表，支持状态过滤
- [x] F3: 消息发送 — Agent 间纯文本消息投递
- [x] F4: 消息接收 — 收件箱查询，支持分页和未读过滤，自动标记已读
- [x] F5: Agent 详情 — 查看指定 Agent 的简介、提示词等完整信息

### 2.2 扩展功能（后续迭代）

- [ ] E1: Agent 状态自动检测（心跳机制）
- [ ] E2: 消息推送/回调通知
- [ ] E3: 联系人分组与权限控制
- [ ] E4: 支持结构化消息（JSON payload）

### 2.3 非功能需求
- 性能：消息写入 < 10ms，列表查询 < 50ms
- 安全：不暴露内部 API，仅通过 tool 接口调用
- 可用性：SQLite WAL 模式，支持并发读

## 3. 用户故事

### US-1: Agent 发送消息
**作为** 一个 Agent
**我想要** 调用 `send_message` 向另一个 Agent 发送纯文本消息
**以便** 完成 Agent 间的任务协作和信息传递

**验收标准：**
- [ ] 传入目标 Agent ID 和文本内容，返回消息 ID 和发送时间
- [ ] 目标 Agent 不存在时返回明确错误
- [ ] 发送方 ID 由运行上下文自动注入，无需显式传入

### US-2: Agent 查收消息
**作为** 一个 Agent
**我想要** 调用 `receive_message` 查看收件箱
**以便** 获取其他 Agent 发给我的消息

**验收标准：**
- [ ] 支持分页（limit / offset）
- [ ] 支持仅查未读消息（unread_only=True）
- [ ] 接收消息时自动将消息标记为已读
- [ ] 返回消息包含发送方名称

### US-3: 查看通讯录
**作为** 一个 Agent
**我想要** 调用 `get_contacts` 查看全局 Agent 列表
**以便** 知道有哪些 Agent 存在以及它们的状态

**验收标准：**
- [ ] 返回所有 Agent（排除自己）
- [ ] 支持按状态过滤（online / offline / busy）

### US-4: 查看 Agent 详情
**作为** 一个 Agent
**我想要** 调用 `get_contact_detail` 查看指定 Agent 的详细资料
**以便** 了解该 Agent 的职责和能力

**验收标准：**
- [ ] 返回 Agent 的 name、desc、prompt、status
- [ ] Agent 不存在时返回错误

### US-5: 管理 Agent 生命周期
**作为** 系统管理员
**我想要** 通过 tool 或外部 API 创建/删除 Agent
**以便** 动态管理多 Agent 团队

**验收标准：**
- [ ] `create_agent` 创建 Agent 并写入 SQLite
- [ ] `delete_agent` 删除 Agent（不级联删除消息，保留历史）
- [ ] 同名 Agent 创建需提示冲突

## 4. 数据模型

### Agent 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 唯一标识，如 "agent-001" |
| name | TEXT NOT NULL | Agent 名称 |
| desc | TEXT | 简介，供其他 Agent 识别用途 |
| prompt | TEXT | 系统提示词 |
| status | TEXT DEFAULT 'offline' | online / offline / busy |
| created_at | TEXT | ISO8601 创建时间 |
| updated_at | TEXT | ISO8601 更新时间 |

### Message 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 消息唯一标识（UUID） |
| sender_id | TEXT FK → Agent | 发送方 Agent ID |
| receiver_id | TEXT FK → Agent | 接收方 Agent ID |
| content | TEXT NOT NULL | 纯文本消息体 |
| is_read | INT DEFAULT 0 | 0=未读, 1=已读 |
| created_at | TEXT | ISO8601 创建时间 |

## 5. Tool 方法签名

| Tool | 参数 | 返回 |
|------|------|------|
| `send_message` | to_agent_id, content | MessageResult |
| `receive_message` | limit=20, offset=0, unread_only=False | list[MessageResult] |
| `get_contacts` | status=None | list[ContactSummary] |
| `get_contact_detail` | agent_id | ContactDetail |
| `create_agent` | name, desc, prompt | Agent |
| `delete_agent` | agent_id | bool |

## 6. 约束与假设

### 6.1 技术约束
- 数据库：SQLite，WAL 模式
- 语言：Python 3.12+
- 框架：无 ORM，使用标准库 `sqlite3`
- 项目结构：遵循 intelliagent 现有架构（`src/core/`、`src/tools/` 等）

### 6.2 业务约束
- 消息永久存储，不支持删除
- 通讯录全局可见，无权限控制
- Agent 删除保留消息历史

### 6.3 假设
- 当前 Agent ID 由运行上下文注入（如环境变量或 engine 传参）
- 消息收发为同步操作，无需消息队列

## 7. 不在范围内
- Agent 间文件传输
- 消息加密
- 群聊/广播
- 消息已读回执通知
- 实时 WebSocket 推送
- Agent 状态自动心跳检测

## 8. 附录
- 参考：intelliagent 现有架构（`src/core/engine.py`、`src/tools/`）
