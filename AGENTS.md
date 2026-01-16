# AGENTS.md（IntelliAgent 仓库指引）

本文件用于指导智能代理在本仓库内安全、可验证地修改代码。
所有说明以仓库现有实现为准，未配置的工具不要臆测。

## 范围

- 适用目录：仓库根目录及其子目录
- 语言：Python 3
- 测试框架：pytest
- 默认测试参数：`pytest.ini` 中 `addopts = -q`

## 依赖与环境

- 安装依赖：`pip install -r requirements.txt`
- 运行前请配置 `.env`（可参考 `.env.example`）
- 关键环境变量（见 `utils/config.py`）：
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL`
  - `MAX_PDCA_CYCLES`
  - `MAX_RETRY_PER_STEP`
  - `MCP_CONFIG_FILE`

## 构建与运行

- 本项目为 Python 脚本型项目，无专门构建步骤
- 典型运行方式：
  - `python main.py "创建一个 Python 文件并写入 Hello World"`
- 交互示例（若存在 `example.py`）：
  - `python example.py`

## 测试命令

- 运行全部测试：
  - `pytest`
- 运行单文件测试：
  - `pytest test/test_intelliagent.py`
- 运行单个测试用例（推荐写法）：
  - `pytest test/test_intelliagent.py::TestLLMClient::test_chat`
- 若需要显示更详细输出，可加 `-vv`（仓库默认 `-q`）

## Lint / 格式化

- 仓库中未发现明确的 lint/format 工具配置（如 ruff/black/isort）
- 除非任务明确要求，请不要引入新的格式化依赖或修改锁文件
- 保持与既有文件一致的缩进、换行与布局风格

## 代码组织与入口

- 主入口：`main.py`
- 核心模块位于 `core/`：
  - `planner.py` / `executor.py` / `checker.py` / `actor.py`
  - `pdca_loop.py` / `react_loop.py` / `llm_client.py`
- 工具与配置位于 `utils/`：
  - `logger.py` 统一日志
  - `config.py` 环境变量配置
- 测试位于 `test/`

## 代码风格与约定

### 通用格式

- 使用 4 空格缩进
- 模块顶部保留模块级 docstring（多为中文）
- 类与函数保留简洁 docstring，描述职责与参数
- 适度换行避免单行过长，保持可读性优先

### 导入规范

- 先标准库，再第三方，再本地模块
- 同一层级导入按字母顺序排列
- 避免循环依赖；需要时延迟导入并说明原因

### 命名规范

- 类：`CamelCase`
- 函数与变量：`snake_case`
- 常量：`UPPER_SNAKE_CASE`
- 私有成员使用前导下划线 `_name`

### 类型与数据结构

- 公共方法优先使用类型注解（`typing` 中的 `List`/`Dict`/`Any`）
- 返回值尽量明确，不返回混合类型
- 对外接口返回结构保持稳定（例如 `run` 返回字典结构）

### 日志与错误处理

- 使用 `utils.logger.logger` 统一日志输出
- 可预期错误：记录 `logger.error` 并返回可诊断信息
- 不吞异常：需要继续上抛时保留原始异常
- 失败分支返回结构化结果（`success`/`error`/`summary`）

### 流程与职责

- 维持 PDCA 责任分层：Plan/Do/Check/Act 分离
- 组件初始化在 `IntelliAgent._initialize_components` 中集中完成
- 新功能优先放到对应核心模块，不要挤入 `main.py`

### 测试约定

- 测试类以 `Test` 开头
- 测试函数命名清晰表达意图
- 需要 mock 时使用 `unittest.mock`
- 文件/路径操作使用 `tmp_path` 避免污染仓库

## 变更建议与边界

- 遵循最小变更原则，避免跨目录大改动
- 不要随意修改 `.env`、`mcp_config.json` 等配置文件
- 如需新增依赖，必须说明必要性与替代方案
- 公共 API 变更需注明兼容性影响

## Cursor / Copilot 规则

- 未发现 `.cursor/rules/`、`.cursorrules` 或 `.github/copilot-instructions.md`
- 若后续新增，请将其要点补充到本文件

## 常见排查建议

- API Key 缺失：检查 `.env` 中 `OPENAI_API_KEY`
- MCP 工具不可用：检查 `MCP_CONFIG_FILE` 路径与 JSON 结构
- 测试失败：优先运行对应单测定位问题

## 文档参考

- `README.md`：项目概览与运行示例
- `docs/`：架构与使用说明（如存在）

## 维护说明

- 本文件面向代理工具，请保持内容简明、可执行
- 如新增测试/工具，请同步更新本文件
