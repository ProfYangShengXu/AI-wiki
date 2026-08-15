/// 后端统一错误码常量，与 `bobanana/errors.py` 保持一致。
///
/// 格式：`SW-<DOMAIN>-<CODE>`，DOMAIN 标识业务域，CODE 通常为 HTTP 状态码
/// 数字或简短标识（UPSTREAM/TIMEOUT/NETWORK）。
///
/// 该文件是客户端侧对后端错误码的“快照”。后端新增错误码时，应同步更新此处
/// 常量与 [descriptions] 映射。
class ErrorCodes {
  ErrorCodes._();

  // ── AUTH ────────────────────────────────────────────────
  /// 未授权 / Bearer Token 缺失或无效
  static const swAuth001 = 'SW-AUTH-001';

  // ── CARD ────────────────────────────────────────────────
  /// 卡片请求参数非法
  static const swCard400 = 'SW-CARD-400';

  /// 卡片不存在
  static const swCard404 = 'SW-CARD-404';

  /// 卡片生成 / 处理失败
  static const swCard500 = 'SW-CARD-500';

  // ── UPLOAD ──────────────────────────────────────────────
  /// 不支持的文件类型 / 内容与扩展名不匹配
  static const swUpload400 = 'SW-UPLOAD-400';

  /// 文件超过大小限制
  static const swUpload413 = 'SW-UPLOAD-413';

  /// 文件解析 / 导入失败
  static const swUpload500 = 'SW-UPLOAD-500';

  // ── QUIZ ────────────────────────────────────────────────
  /// Quiz 请求非法（如无有效卡片）
  static const swQuiz400 = 'SW-QUIZ-400';

  /// 卡片不存在（Quiz 上下文）
  static const swQuiz404 = 'SW-QUIZ-404';

  /// 生成 / 评分 / 合并 / 组卷失败
  static const swQuiz500 = 'SW-QUIZ-500';

  // ── TASK ────────────────────────────────────────────────
  /// 上传任务不存在
  static const swTask404 = 'SW-TASK-404';

  // ── SETTINGS ────────────────────────────────────────────
  /// 非法配置项 / 掩码 Key / 非法供应商
  static const swSettings400 = 'SW-SETTINGS-400';

  // ── KNOWLEDGEBASE ───────────────────────────────────────
  /// 非法操作（如删除默认知识库）
  static const swKb400 = 'SW-KB-400';

  /// 知识库不存在
  static const swKb404 = 'SW-KB-404';

  /// 知识库切换失败
  static const swKb500 = 'SW-KB-500';

  // ── BOOTSTRAP ───────────────────────────────────────────
  /// 占位 Key / 请求非法
  static const swBootstrap400 = 'SW-BOOTSTRAP-400';

  /// API Key 无效或未授权
  static const swBootstrap401 = 'SW-BOOTSTRAP-401';

  /// 请求过于频繁或额度不足
  static const swBootstrap429 = 'SW-BOOTSTRAP-429';

  /// 上游模型服务返回异常状态码
  static const swBootstrapUpstream = 'SW-BOOTSTRAP-UPSTREAM';

  /// 验证超时
  static const swBootstrapTimeout = 'SW-BOOTSTRAP-TIMEOUT';

  /// 无法连接模型服务
  static const swBootstrapNetwork = 'SW-BOOTSTRAP-NETWORK';

  // ── GENERIC ─────────────────────────────────────────────
  static const swGeneric400 = 'SW-GENERIC-400';
  static const swGeneric401 = 'SW-GENERIC-401';
  static const swGeneric403 = 'SW-GENERIC-403';
  static const swGeneric404 = 'SW-GENERIC-404';
  static const swGeneric405 = 'SW-GENERIC-405';
  static const swGeneric409 = 'SW-GENERIC-409';
  static const swGeneric413 = 'SW-GENERIC-413';
  static const swGeneric422 = 'SW-GENERIC-422';
  static const swGeneric500 = 'SW-GENERIC-500';
  static const swGeneric502 = 'SW-GENERIC-502';
  static const swGeneric503 = 'SW-GENERIC-503';
  static const swGeneric504 = 'SW-GENERIC-504';

  /// 全部错误码（供文档/校验/测试使用）。
  static const all = <String>[
    swAuth001,
    swCard400,
    swCard404,
    swCard500,
    swUpload400,
    swUpload413,
    swUpload500,
    swQuiz400,
    swQuiz404,
    swQuiz500,
    swTask404,
    swSettings400,
    swKb400,
    swKb404,
    swKb500,
    swBootstrap400,
    swBootstrap401,
    swBootstrap429,
    swBootstrapUpstream,
    swBootstrapTimeout,
    swBootstrapNetwork,
    swGeneric400,
    swGeneric401,
    swGeneric403,
    swGeneric404,
    swGeneric405,
    swGeneric409,
    swGeneric413,
    swGeneric422,
    swGeneric500,
    swGeneric502,
    swGeneric503,
    swGeneric504,
  ];

  /// 错误码 → 用户可读说明（与后端 `ERROR_CODE_DESCRIPTIONS` 对齐）。
  static const descriptions = <String, String>{
    swAuth001: '未授权：Authorization Bearer Token 缺失或无效',
    swCard400: '卡片请求参数非法',
    swCard404: '卡片不存在',
    swCard500: '卡片生成或处理失败',
    swUpload400: '不支持的文件类型或文件内容与扩展名不匹配',
    swUpload413: '文件超过 100MB 大小限制',
    swUpload500: '文件解析或导入失败',
    swQuiz400: 'Quiz 请求非法（如无有效卡片）',
    swQuiz404: '卡片不存在（Quiz 上下文）',
    swQuiz500: 'Quiz 生成、评分、合并或组卷失败',
    swTask404: '上传任务不存在',
    swSettings400: '非法配置项、掩码 Key 或非法供应商',
    swKb400: '非法知识库操作（如删除默认知识库）',
    swKb404: '知识库不存在',
    swKb500: '知识库切换失败',
    swBootstrap400: '请求非法（如占位 API Key）',
    swBootstrap401: 'API Key 无效或未授权',
    swBootstrap429: '请求过于频繁或额度不足',
    swBootstrapUpstream: '上游模型服务返回异常状态码',
    swBootstrapTimeout: '验证 API Key 超时',
    swBootstrapNetwork: '无法连接模型服务',
    swGeneric400: '通用请求错误（Bad Request）',
    swGeneric401: '通用未授权（Unauthorized）',
    swGeneric403: '通用禁止访问（Forbidden）',
    swGeneric404: '通用资源不存在（Not Found）',
    swGeneric405: '通用方法不允许（Method Not Allowed）',
    swGeneric409: '通用冲突（Conflict）',
    swGeneric413: '通用请求体过大（Payload Too Large）',
    swGeneric422: '通用校验失败（Unprocessable Entity）',
    swGeneric500: '通用服务器内部错误（Internal Server Error）',
    swGeneric502: '通用上游错误（Bad Gateway）',
    swGeneric503: '通用服务不可用（Service Unavailable）',
    swGeneric504: '通用上游超时（Gateway Timeout）',
  };

  /// 读取错误码的中文说明，未知码返回原文。
  static String describe(String code) => descriptions[code] ?? code;
}

/// 非数字 CODE 后缀 → 默认 HTTP 状态码（与后端 `_NON_NUMERIC_STATUS` 一致）。
const Map<String, int> _nonNumericStatus = {
  'UPSTREAM': 502,
  'TIMEOUT': 504,
  'NETWORK': 503,
};

/// HTTP 状态码 → SW-GENERIC-xxx（与后端 `GENERIC_CODE_BY_STATUS` 一致）。
const Map<int, String> _genericCodeByStatus = {
  400: ErrorCodes.swGeneric400,
  401: ErrorCodes.swGeneric401,
  403: ErrorCodes.swGeneric403,
  404: ErrorCodes.swGeneric404,
  405: ErrorCodes.swGeneric405,
  409: ErrorCodes.swGeneric409,
  413: ErrorCodes.swGeneric413,
  422: ErrorCodes.swGeneric422,
  500: ErrorCodes.swGeneric500,
  502: ErrorCodes.swGeneric502,
  503: ErrorCodes.swGeneric503,
  504: ErrorCodes.swGeneric504,
};

/// 从错误码推导 HTTP 状态码（与后端 `status_for_code` 一致）。
int statusForCode(String code) {
  final parts = code.split('-');
  final suffix = parts.isEmpty ? code : parts.last;
  if (suffix.isNotEmpty && int.tryParse(suffix) != null) {
    return int.parse(suffix);
  }
  return _nonNumericStatus[suffix] ?? 500;
}

/// 将 HTTP 状态码映射为 SW-GENERIC-xxx 错误码（与后端
/// `generic_code_for_status` 一致）。
String genericCodeForStatus(int statusCode) {
  return _genericCodeByStatus[statusCode] ?? 'SW-GENERIC-$statusCode';
}
