"""统一错误码模块 — SWError 异常 + 错误码常量 + sw_raise 助手。

错误码格式: ``SW-<DOMAIN>-<CODE>``
- ``DOMAIN`` 标识业务域（AUTH/CARD/UPLOAD/QUIZ/TASK/SETTINGS/KB/BOOTSTRAP/GENERIC）
- ``CODE`` 通常为 HTTP 状态码数字或简短标识（UPSTREAM/TIMEOUT/NETWORK）

所有错误码在此处集中定义，便于 api/openapi.yaml 与 docs/api.md 同步引用。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NoReturn

# ── 错误码常量 ──────────────────────────────────────────
# AUTH
SW_AUTH_001 = "SW-AUTH-001"          # 未授权 / Bearer Token 缺失或无效

# CARD
SW_CARD_400 = "SW-CARD-400"          # 卡片请求参数非法
SW_CARD_404 = "SW-CARD-404"          # 卡片不存在
SW_CARD_500 = "SW-CARD-500"          # 卡片生成 / 处理失败

# UPLOAD
SW_UPLOAD_400 = "SW-UPLOAD-400"      # 不支持的文件类型 / 内容与扩展名不匹配
SW_UPLOAD_413 = "SW-UPLOAD-413"      # 文件超过大小限制
SW_UPLOAD_500 = "SW-UPLOAD-500"      # 文件解析 / 导入失败

# QUIZ
SW_QUIZ_400 = "SW-QUIZ-400"          # Quiz 请求非法（如无有效卡片）
SW_QUIZ_404 = "SW-QUIZ-404"          # 卡片不存在（Quiz 上下文）
SW_QUIZ_500 = "SW-QUIZ-500"          # 生成 / 评分 / 合并 / 组卷失败

# TASK（上传后台任务）
SW_TASK_404 = "SW-TASK-404"          # 上传任务不存在

# SETTINGS
SW_SETTINGS_400 = "SW-SETTINGS-400"  # 非法配置项 / 掩码 Key / 非法供应商

# KNOWLEDGEBASE
SW_KB_400 = "SW-KB-400"              # 非法操作（如删除默认知识库）
SW_KB_404 = "SW-KB-404"              # 知识库不存在
SW_KB_500 = "SW-KB-500"              # 知识库切换失败

# BOOTSTRAP
SW_BOOTSTRAP_400 = "SW-BOOTSTRAP-400"        # 占位 Key / 请求非法
SW_BOOTSTRAP_401 = "SW-BOOTSTRAP-401"        # API Key 无效或未授权
SW_BOOTSTRAP_429 = "SW-BOOTSTRAP-429"        # 请求过于频繁或额度不足
SW_BOOTSTRAP_UPSTREAM = "SW-BOOTSTRAP-UPSTREAM"  # 上游模型服务返回异常状态码
SW_BOOTSTRAP_TIMEOUT = "SW-BOOTSTRAP-TIMEOUT"    # 验证超时
SW_BOOTSTRAP_NETWORK = "SW-BOOTSTRAP-NETWORK"    # 无法连接模型服务

# AGENT
SW_AGENT_400 = "SW-AGENT-400"          # Agent 工具参数校验失败
SW_AGENT_429 = "SW-AGENT-429"          # Agent 超出预算（turns/tokens/wall time）

# LLM
SW_LLM_503 = "SW-LLM-503"              # 所有 LLM provider 均不可用

# DB（数据库生命周期）
SW_DB_507 = "SW-DB-507"                # 磁盘剩余空间不足, 拒绝写入

# GENERIC（按 HTTP 状态映射，供 HTTPException 包装使用）
SW_GENERIC_400 = "SW-GENERIC-400"
SW_GENERIC_401 = "SW-GENERIC-401"
SW_GENERIC_403 = "SW-GENERIC-403"
SW_GENERIC_404 = "SW-GENERIC-404"
SW_GENERIC_405 = "SW-GENERIC-405"
SW_GENERIC_409 = "SW-GENERIC-409"
SW_GENERIC_413 = "SW-GENERIC-413"
SW_GENERIC_422 = "SW-GENERIC-422"
SW_GENERIC_500 = "SW-GENERIC-500"
SW_GENERIC_502 = "SW-GENERIC-502"
SW_GENERIC_503 = "SW-GENERIC-503"
SW_GENERIC_504 = "SW-GENERIC-504"

# ── 错误码说明（供文档 / OpenAPI 枚举复用）──────────────
ERROR_CODE_DESCRIPTIONS: dict[str, str] = {
    SW_AUTH_001: "未授权：Authorization Bearer Token 缺失或无效",
    SW_CARD_400: "卡片请求参数非法",
    SW_CARD_404: "卡片不存在",
    SW_CARD_500: "卡片生成或处理失败",
    SW_UPLOAD_400: "不支持的文件类型或文件内容与扩展名不匹配",
    SW_UPLOAD_413: "文件超过 100MB 大小限制",
    SW_UPLOAD_500: "文件解析或导入失败",
    SW_QUIZ_400: "Quiz 请求非法（如无有效卡片）",
    SW_QUIZ_404: "卡片不存在（Quiz 上下文）",
    SW_QUIZ_500: "Quiz 生成、评分、合并或组卷失败",
    SW_TASK_404: "上传任务不存在",
    SW_SETTINGS_400: "非法配置项、掩码 Key 或非法供应商",
    SW_KB_400: "非法知识库操作（如删除默认知识库）",
    SW_KB_404: "知识库不存在",
    SW_KB_500: "知识库切换失败",
    SW_BOOTSTRAP_400: "请求非法（如占位 API Key）",
    SW_BOOTSTRAP_401: "API Key 无效或未授权",
    SW_BOOTSTRAP_429: "请求过于频繁或额度不足",
    SW_BOOTSTRAP_UPSTREAM: "上游模型服务返回异常状态码",
    SW_BOOTSTRAP_TIMEOUT: "验证 API Key 超时",
    SW_BOOTSTRAP_NETWORK: "无法连接模型服务",
    SW_AGENT_400: "Agent 工具参数校验失败",
    SW_AGENT_429: "Agent 超出预算限制（turns/tokens/wall time）",
    SW_LLM_503: "所有 LLM provider 均不可用",
    SW_DB_507: "磁盘剩余空间不足，拒绝写入",
    SW_GENERIC_400: "通用请求错误（Bad Request）",
    SW_GENERIC_401: "通用未授权（Unauthorized）",
    SW_GENERIC_403: "通用禁止访问（Forbidden）",
    SW_GENERIC_404: "通用资源不存在（Not Found）",
    SW_GENERIC_405: "通用方法不允许（Method Not Allowed）",
    SW_GENERIC_409: "通用冲突（Conflict）",
    SW_GENERIC_413: "通用请求体过大（Payload Too Large）",
    SW_GENERIC_422: "通用校验失败（Unprocessable Entity）",
    SW_GENERIC_500: "通用服务器内部错误（Internal Server Error）",
    SW_GENERIC_502: "通用上游错误（Bad Gateway）",
    SW_GENERIC_503: "通用服务不可用（Service Unavailable）",
    SW_GENERIC_504: "通用上游超时（Gateway Timeout）",
}

# ── 非数字 CODE 后缀 → 默认 HTTP 状态码 ────────────────
_NON_NUMERIC_STATUS: dict[str, int] = {
    "UPSTREAM": 502,
    "TIMEOUT": 504,
    "NETWORK": 503,
}

# ── HTTP 状态码 → SW-GENERIC-xxx（供 HTTPException 包装） ─
GENERIC_CODE_BY_STATUS: dict[int, str] = {
    400: SW_GENERIC_400,
    401: SW_GENERIC_401,
    403: SW_GENERIC_403,
    404: SW_GENERIC_404,
    405: SW_GENERIC_405,
    409: SW_GENERIC_409,
    413: SW_GENERIC_413,
    422: SW_GENERIC_422,
    500: SW_GENERIC_500,
    502: SW_GENERIC_502,
    503: SW_GENERIC_503,
    504: SW_GENERIC_504,
}


def status_for_code(code: str) -> int:
    """从错误码推导 HTTP 状态码。

    形如 ``SW-CARD-404`` 的数值后缀直接作为状态码；
    非数值后缀（UPSTREAM/TIMEOUT/NETWORK）按映射表回退，其余回退 500。
    """
    suffix = code.rsplit("-", 1)[-1] if "-" in code else code
    if suffix.isdigit():
        return int(suffix)
    return _NON_NUMERIC_STATUS.get(suffix, 500)


def generic_code_for_status(status_code: int) -> str:
    """将 HTTP 状态码映射为 SW-GENERIC-xxx 错误码。"""
    return GENERIC_CODE_BY_STATUS.get(status_code, f"SW-GENERIC-{status_code}")


def utc_now_iso() -> str:
    """ISO8601 UTC 时间戳（与 ApiResponse.timestamp 保持一致）。"""
    return datetime.now(UTC).isoformat()


class SWError(Exception):
    """统一业务异常。

    字段:
    - ``status_code``: HTTP 状态码
    - ``error_code``: 形如 ``SW-<DOMAIN>-<CODE>``
    - ``message``: 面向用户的错误信息
    - ``detail``: 可选调试详情（默认不写入响应体，仅用于日志）
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int | None = None,
        detail: str | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code if status_code is not None else status_for_code(error_code)
        self.detail = detail
        super().__init__(message)

    def to_dict(self) -> dict:
        """转换为统一错误响应体（不含 detail）。"""
        return {
            "status": "error",
            "error_code": self.error_code,
            "message": self.message,
            "timestamp": utc_now_iso(),
        }


def sw_raise(code: str, message: str, status_code: int | None = None) -> NoReturn:
    """抛出 SWError。

    :param code: 错误码，如 ``SW-CARD-404``。
    :param message: 面向用户的错误信息。
    :param status_code: 可选 HTTP 状态码；缺省时按错误码数值后缀推导。
    """
    raise SWError(error_code=code, message=message, status_code=status_code)
