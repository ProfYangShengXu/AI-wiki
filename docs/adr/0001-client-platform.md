# ADR-0001: Android / Windows 客户端技术选型

- 状态：建议（P0 评审后定稿）
- 日期：2026-07-15
- 决策者：项目负责人 + 客户端 owner
- 关联文档：`docs/next-phase-optimization.md` W1

## 背景

StudyWiki-Agent 当前前端是 `static/index.html` 单文件网页。Phase 2 要求重写为 Android 与 Windows 第一方应用，同时保留 Web 作为轻量兼容入口。项目文档 `docs/plan.md` 按 1 人全栈估算，UI 技术选型必须优先考虑单码库与迭代速度。

## 候选方案

| 方案 | Android | Windows | UI 复用 | 风险 |
| --- | --- | --- | --- | --- |
| A. Flutter（推荐） | Flutter/Dart | Flutter/Dart | 单码库 | Windows 托盘、进程托管、文件关联需平台通道验证 |
| B. 双原生 | Kotlin + Compose | C# + WinUI 3 | 两套 UI | 人力成本最高，双端一致性难保证 |
| C. KMP + Compose Multiplatform | Kotlin/Compose | Kotlin/Compose Desktop | 高 | Windows 打包与生态成熟度弱于 Flutter/WinUI |

## 决策

**默认采用方案 A（Flutter 单码库）**，产出 Android 与 Windows 客户端；共享层为：

1. `api/openapi.yaml` 与 WebSocket 事件字典；
2. Material 3 设计令牌与组件规范；
3. 统一错误码与任务状态机；
4. `study-wiki-core` FastAPI 服务契约。

理由：

- 本项目为 1 人全栈团队，单码库最现实。
- 客户端不依赖深度 OS 能力，主要是 HTTP/WebSocket、文件选择、本地缓存、通知与打包。
- Windows 端需要额外能力（启动/停止 sidecar、托盘、文件关联、MSIX 更新）通过少量 platform channels 实现，复杂度可控。
- 现有 Web 入口保留，降低迁移期风险。

## P0 探针（第 0 周必须完成）

1. Windows：Flutter 应用启动外部进程（sidecar）、读写本地文件、WebSocket 长连接、MSIX 打包安装。
2. Android：WebSocket 长连接、局域网 HTTP、本地 SQLite/文件缓存、AAB 构建。

若探针 1 失败（尤其是 sidecar 进程管理或 MSIX），则 Windows 端回退 WinUI 3（方案 B 的 Windows 分支），Android 保持 Flutter 或 Kotlin 原生。

## 后果

### 正面

- UI 只维护一套，迭代和 E2E 成本最低。
- Android/Windows 同步交付，视觉一致。

### 代价

- Windows 端平台能力需要 platform channels，遇到 Flutter 插件缺陷时排查成本较高。
- 需要新增 Dart/Flutter 技能，或接受学习曲线。

## 验收

- [ ] 两个平台均可从仓库一键构建安装包。
- [ ] 双端核心旅程“连接服务 → 浏览卡片 → 提问 → Quiz → 掌握度”自动化 E2E 通过。
- [ ] P0 探针结果与最终决策回写本 ADR。
