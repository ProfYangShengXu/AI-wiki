# StudyWiki-Agent 工程化差距报告

> 快照说明：本报告基于当前工作区代码一次性采集生成。仓库无 git 且
> `bobanana/` 由多个 agent 并行修改，因此下列数字为**生成时刻的快照**，
> 后续代码变更可能导致数值漂移；第 4 轮清零时应以最新一次 CI 运行为准。

## 0. 工具与配置版本

| 工具 | 版本 | 用途 |
| --- | --- | --- |
| ruff | 0.16.3 | 代码风格 / 静态检查 |
| mypy | 2.3.1 | 类型检查 |
| pytest | 9.1.1 | 测试运行 |
| pytest-cov | 7.1.0 | 覆盖率（基于 coverage 7.15.4） |
| pytest-xdist | 3.8.0 | 测试并行执行 |

采集命令：

```bash
.venv-linux/bin/python -m ruff check bobanana tests scripts
.venv-linux/bin/python -m mypy bobanana
```

---

## 1. ruff 违规统计

启用规则族（`[tool.ruff.lint] select`）：`E` / `F` / `W` / `I` / `UP` / `B`；
`line-length = 110`，`target-version = py311`。

因与既有风格冲突而在 `ignore` 中豁免的规则（详见 `pyproject.toml` 注释）：

| 规则 | 当前数量 | 豁免理由 |
| --- | --- | --- |
| E701 | 36 | 单行 `if x: return y` 紧凑写法，既有风格 |
| E402 | 7 | 模块级 import 不在顶部（tools.py 等延迟/局部导入） |
| E702 | 1 | 单行分号语句，同上 |
| B008 | 1 | FastAPI 默认参数里直接 `File()`/`Depends()`，框架惯用法 |

### 1.1 当前违规（启用规则内，共 145 条）

```
 42  UP045   non-pep604-annotation-optional     （Optional[X] 未改写为 X | None）
 39  I001    unsorted-imports                   （import 未按 isort 排序）
 20  E501    line-too-long                      （行长 > 110）
 14  UP017   datetime-timezone-utc              （utcnow() 等无时区 API）
 11  F401    unused-import                      （未使用 import）
  7  B904    raise-without-from-inside-except   （except 内 raise 未用 from）
  2  E722    bare-except                        （裸 except:）
  2  UP015   redundant-open-modes               （open() 冗余的 "r" 模式）
  2  UP035   deprecated-import                  （如 typing.List -> list 的旧导入）
  1  B905    zip-without-explicit-strict        （zip() 未显式 strict=）
  1  E401    multiple-imports-on-one-line
  1  E741    ambiguous-variable-name            （单字符 l/I/O 变量名）
  1  UP006   non-pep585-annotation
  1  UP012   unnecessary-encode-utf8
  1  UP037   quoted-annotation
```

合计：**145 条**，其中 `114 条可用 --fix 自动修复`（多为 I001 / F401 / UP 系列）。
若把豁免规则也算上，原始违规约 190 条。

### 1.2 代表性摘录（截断）

```
bobanana/tools.py:133:  E501  Line too long (…)
bobanana/agent.py:…:    E701  Multiple statements on one line (colon)   # 已在 ignore 中豁免
bobanana/tools.py:4:1:  E402  Module level import not at top of file   # 已在 ignore 中豁免
bobanana/routes/upload.py:70:42: B008  Do not perform function call `File` in argument defaults  # 已在 ignore 中豁免
```

---

## 2. mypy 类型检查

配置：`python_version = 3.11`、`ignore_missing_imports = true`、
`no_site_packages = true`、`disallow_untyped_defs = false`、
`disallow_incomplete_defs = false`、`check_untyped_defs = true`。

> **重要决策 —— 为什么 `no_site_packages = true`**：
> 当前环境安装的 numpy 2.x 自带 PEP 695（`type X = ...`）类型桩，而 mypy
> 目标 `python_version = 3.11` 时无法解析该语法，会在读取 `numpy/__init__.pyi`
> 时直接报 `[syntax]` 错误并中断检查（`numpy` 仅在 `card_service.py` 内懒加载，
> 却会拖垮整个 `mypy bobanana`）。关闭 site-packages 查找后，第三方包统一按
> `Any` 处理，mypy 只对 `bobanana/` 自身代码做检查，契合「宽松起步」定位。

结果：**61 条错误 / 11 个文件**（检查 26 个源文件）。

### 2.1 按错误码统计

| 错误码 | 数量 | 含义 |
| --- | --- | --- |
| union-attr | 22 | 可选值（`X | None`）未判空直接调属性 |
| index | 14 | 对不可索引类型（`object` / `Match[str] | None`）取下标 |
| assignment | 7 | 赋值类型不兼容（如 `float` -> `int`） |
| attr-defined | 6 | 类型上不存在该属性 |
| var-annotated | 3 | 变量需要显式类型注解 |
| operator | 3 | 操作数类型不支持该运算符 |
| misc | 3 | 其它（lambda 无法推断、except 外使用 e 等） |
| arg-type | 3 | 实参与形参类型不匹配 |

### 2.2 按文件统计（Top 集中点）

| 文件 | 错误数 |
| --- | --- |
| bobanana/routes/quiz.py | 21 |
| bobanana/database.py | 18 |
| bobanana/agent_react.py | 7 |
| bobanana/tools_schema.py | 6 |
| bobanana/tools.py | 3 |
| bobanana/retrieval.py | 3 |
| bobanana/agent.py | 2 |
| 其余 4 文件各 1 | 4 |

### 2.3 代表性摘录（截断）

```
bobanana/database.py:69:  error: Item "None" of "Any | None" has no attribute "add"  [union-attr]
bobanana/database.py:198: error: Incompatible types in assignment (expression has type "int | None", variable has type "int")  [assignment]
bobanana/retrieval.py:198: error: Incompatible types in assignment (expression has type "float", target has type "int")  [assignment]
bobanana/routes/quiz.py:256: error: Incompatible types in assignment (expression has type "dict[Any, Any]", variable has type "Match[str] | None")  [assignment]
bobanana/tools.py:133: error: Need type annotation for "pages"  [var-annotated]
```

---

## 3. Top 10 高频问题（合并视角）

1. **`Optional[X]` 未用 PEP 604 写法**（UP045，42 处）——可 `--fix` 自动改写。
2. **import 未排序**（I001，39 处）——可 `--fix`。
3. **单行多语句紧凑写法**（E701，36 处，已豁免）——既有风格，第 4 轮可评估是否拆开。
4. **可选值未判空直接调用**（mypy union-attr，22 处，集中在 `database.py`/`quiz.py`）。
5. **行长超 110**（E501，20 处）。
6. **无时区 datetime API**（UP017，14 处，`utcnow()` 等）——需人工确认时区语义。
7. **对 `object` / 联合类型取下标**（mypy index，14 处，集中在 `quiz.py`/`agent_react.py`）。
8. **未使用的 import**（F401，11 处）——可 `--fix`。
9. **except 内 raise 未链 `from`**（B904，7 处）——需人工修复。
10. **`quiz.py` 局部变量遮蔽**（`Match[str] | None` 被复用为 dict，21 处错误的最大来源）。

---

## 4. 第 4 轮清零行动建议清单

### 4.1 ruff 快速自动化（先做，收益大）

```bash
# 1) 自动修复 import 排序 / 未用 import / Optional->|None 等
.venv-linux/bin/python -m ruff check bobanana tests scripts --fix
# 2) 复查剩余的 UP006/UP017/UP035 等，按需 --unsafe-fixes 逐条人工确认
.venv-linux/bin/python -m ruff check bobanana tests scripts --statistics
```

- I001 / F401 / UP045 / UP015 / UP035 / UP012 / UP037 / UP006：`--fix` 即可清零。
- E501：`--fix` 部分可拆，剩余手动换行。
- B904 / E722 / B905：需人工确认语义后修复（不建议无脑自动）。
- 豁免的 E701/E702/E402/B008：第 4 轮重新评估是否逐条拆分后移除 ignore。

### 4.2 mypy 收紧路线（建议顺序）

1. 先清零 `assignment` / `operator` / `arg-type`（数量少、语义明确，如
   `retrieval.py` 的 `float -> int`、`chat.py` 的 `Any | None -> str`）。
2. 处理 `union-attr` / `index` / `attr-defined`（对 `object`/`X | None` 加显式
   类型断言或判空；`quiz.py` 的 `Match` 变量遮蔽建议重命名为 `mastery` 字典）。
3. 补 `var-annotated` 的 3 处显式注解（`tools.py:133/218`、`agent.py:366`）。
4. 全部清零后收紧配置：`disallow_untyped_defs = true` →
   `disallow_incomplete_defs = true` → 最终 `strict = true`。

### 4.3 coverage 与 CI 阈值

- 当前 `[tool.coverage.report]` 未设 `fail_under`；第 4 轮建立基线后设为 80。
- 覆盖报告已开启 `show_missing` + `skip_covered`，CI 上传 `coverage.xml` 工件
  供本地/云端查看逐行缺失。
- 待 bobanana 收敛后再评估是否把 `-n auto`（xdist）与 `test_e2e.py`
  共享 ChromaDB 全局状态冲突的用例串行化。
