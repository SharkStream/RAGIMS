# A4 · 阶段 A 验收标准

> **阶段**：A 项目脚手架与基础设施　**依赖**：A1、A2、A3

## 验收清单

- [ ] 访问 `/docs` 与 `/healthz` 正常返回。
- [ ] CI（GitHub Actions 最小流水线）能跑通 lint + 单测。
- [ ] 后端目录分层、统一日志、统一配置、pre-commit 全部就位。

## 达成标志

阶段 A 完成后，项目具备可运行、可测试、可一键复现的工程骨架，为 M1「环境就绪」里程碑（第 1 周末）提供支撑。

## 关联任务

- 上游：[A1](a1-repo-structure.md)、[A2](a2-local-env.md)、[A3](a3-fastapi-skeleton.md)。
- 下游：全部进入 [B 数据模型](b1-db-tables.md)。
