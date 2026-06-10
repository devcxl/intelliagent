# Web 文档迁移说明

> **文档状态**：迁移说明  
> 旧版 Web 更新说明基于历史实现路径（如 `src/web/server.py`、`web/frontend/`）编写，已不再代表统一规划方向。  
> 当前统一规划请见 [plan.md](./plan.md)。

---

## 说明

此前 Web 相关文档主要围绕以下旧实现展开：

- 旧后端入口与旧脚本
- 旧前端目录路径
- 以日志为中心的界面描述

这些内容已与当前收敛目标不一致。

---

## 现在应参考的文档

- [plan.md](./plan.md)：统一实施蓝图
- [WEB_UI.md](./WEB_UI.md)：Web 模式目标形态
- [QUICK_START_WEB.md](./QUICK_START_WEB.md)：Web 模式推荐启动路径
- [VERIFICATION.md](./VERIFICATION.md)：统一验证口径

---

## 迁移原则

- Web 是入口模式，不是唯一产品形态
- Web 与 CLI 必须共用一套核心执行链
- 前端路径统一收敛到 `frontend/`
- Web 入口统一收敛到 `src/app.py`
