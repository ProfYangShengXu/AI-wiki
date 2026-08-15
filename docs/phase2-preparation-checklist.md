# StudyWiki-Agent Phase 2 前期准备清单（P0）

> 对应 `docs/next-phase-optimization.md` 第 12 节。  
> 完成项已按当前仓库状态勾选（2026-08-15 盘点）。

## 1. 仓库止血与基线

- [ ] 打基线标签：`git tag v0.3.0-phase2-baseline`（工作区无 .git，交付后由仓库持有者执行）
- [x] 确认 `bobanana.app` 可被 `python -c "import bobanana.app"` 正常导入（F1 临时修复验证）
- [x] 清理根目录大文件：`ltspice_installer.msi` 已移出
- [x] 清理 `tmp/`、`logs/`、测试残留；确认 `.gitignore` 生效（已补 tmp/、data/、backups/、docs/eval/results/）
- [x] 补充 `.gitattributes`（二进制与换行规则）

## 2. 工程化底座

- [x] 在 `pyproject.toml` 增加 ruff、mypy、pytest-cov、pytest-xdist 配置（R1-B 交付）
- [x] 建立 `tests/fakes.py`：FakeLLM、FakeEmbeddings、FakeProgress（R1-A 扩展 quiz 响应）
- [x] 建立 `tests/conftest.py`：`tmp_path` ChromaDB 夹具，禁止测试使用生产 `chroma_db/`
- [x] 将 Quiz/评分/生成等真实 LLM 测试迁移到 FakeLLM；真实模型测试标记 `@llm` 且默认跳过（无 Key 全绿已验证：137 passed）
- [x] 建立 `.github/workflows/ci.yml`：lint → type → unit → contract → api-e2e → coverage（R1-B 交付）
- [x] 目标：现有测试在无网络、无 API Key 环境下可运行（已实测通过）

## 3. 契约与架构

- [x] 评审/确认 `docs/adr/0001-client-platform.md`（Flutter vs 双原生，维持 Flutter 单码库）
- [ ] 完成 Flutter Windows 探针：托盘/启动 sidecar/WebSocket/MSIX 打包（本环境无 Windows/Flutter SDK，由 CI windows-latest 构建产物替代验证）
- [x] 冻结 `api/openapi.yaml` v1（30 path / 30 schema，与路由一致）
- [x] 冻结 WebSocket 事件字典：`llm.delta`、`tool.called`、`approval_required` 等（见 phase2-implementation-contract.md §1.4）
- [x] 定义统一错误码：`SW-<DOMAIN>-<CODE>`（bobanana/errors.py 集中定义）
- [x] 定义本地鉴权方案：可选 Bearer Token（STUDYWIKI_AUTH_TOKEN）+ 设备配对契约（客户端侧已实现，服务端 /api/pair/* 待补）

## 4. 安全与数据

- [x] 设置页 Key 脱敏：只显示末 4 位，禁止明文返回（R1-C/A 验证）
- [x] `save_setting` 增加 key 白名单校验
- [x] CORS 从 `*` 改为本地客户端白名单
- [x] 上传增加大小限制、扩展名+魔数校验、UUID 文件名
- [ ] ChromaDB 迁移/备份脚本：迁移前自动备份，支持 dry-run 与回滚（R2-G 进行中）

## 5. Agent 与评测资产

- [x] 收集 10 份小型文档夹具（PDF/Word/MD，脱敏课程内容，docs/eval/fixtures/）
- [x] 建立 20 条固定 Agent 评测指令（创建/查询/修改/删除/Quiz/组卷/导入，docs/eval/agent_instructions.jsonl）
- [x] 建立 50 条中文检索标注集（问题 → 期望卡片，docs/eval/retrieval_queries.jsonl）
- [x] 定义 Agent 指标报告模板：成功率、工具准确率、参数合法率、Token 成本（docs/eval/README.md）
- [x] 冻结导入任务状态机：`queued → scanning → extracting → linking → done/failed/cancelled`（R2-E 实现中）

## 6. 客户端与发布

- [ ] 确认 Android 签名证书与内部测试/Play 账号（需仓库持有者提供）
- [ ] 确认 Windows MSIX 签名方式（开发证书或代码签名）（需仓库持有者提供）
- [ ] 确认 Windows 自动更新通道（需仓库持有者决策）
- [ ] 准备双端设计资源：图标、启动页、主题色、中英文文案表
- [ ] 准备 5 名可用性测试用户与任务脚本

## 7. P0 完成定义

- [x] `python -c "import bobanana.app"` 成功
- [x] 无 API Key 环境下 `pytest` 全绿（或仅预期跳过）——137 passed 实测
- [ ] CI 在 PR 上跑通 lint + unit + contract + api-e2e（工作流已就绪，需推送 GitHub 后生效）
- [x] 设置 API 不再泄露 API Key
- [x] OpenAPI v1 与 ADR 已评审冻结
- [x] M1 开发任务可拆入看板（本清单即看板）
