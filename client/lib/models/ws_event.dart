import 'dart:convert';

/// WebSocket 事件解析（契约 §1.4 流式事件 + 现有 response/progress/error）。
///
/// 该解析器为纯 Dart，便于单元测试；`chat_page` 负责把事件渲染成 UI。
class WsEvent {
  const WsEvent({
    required this.type,
    this.content = '',
    this.data = const {},
  });

  /// 服务端推送的增量文本（`llm.delta`）。
  static const typeLlmDelta = 'llm.delta';

  /// 工具开始执行（`tool.called`）。
  static const typeToolCalled = 'tool.called';

  /// 工具执行完成（`tool.result`）。
  static const typeToolResult = 'tool.result';

  /// 需要用户审批（`approval_required`）。
  static const typeApprovalRequired = 'approval_required';

  /// 会话开始/完成/出错（`session.started` / `session.done` / `session.error`）。
  static const typeSessionStarted = 'session.started';
  static const typeSessionDone = 'session.done';
  static const typeSessionError = 'session.error';

  /// 现有事件（兼容旧后端）。
  static const typeResponse = 'response';
  static const typeProgress = 'progress';
  static const typeError = 'error';

  final String type;
  final String content;
  final Map<String, dynamic> data;

  /// 从 WS 原始文本解析事件；非法 JSON 返回 null。
  static WsEvent? parse(String raw) {
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return null;
      final type = decoded['type'];
      if (type is! String || type.isEmpty) return null;
      final data = decoded['data'];
      return WsEvent(
        type: type,
        content: decoded['content'] as String? ?? '',
        data: data is Map<String, dynamic> ? data : const {},
      );
    } catch (_) {
      return null;
    }
  }

  // ── 流式事件字段 ────────────────────────────────────────
  String? get delta => data['delta'] as String?;
  String? get sessionId => data['session_id'] as String?;
  String? get tool => data['tool'] as String?;
  Map<String, dynamic> get toolArgs =>
      data['args'] is Map<String, dynamic>
          ? data['args'] as Map<String, dynamic>
          : const {};
  bool get toolOk => data['ok'] == true;
  String? get toolSummary => data['summary'] as String?;
  String? get approvalId => data['approval_id'] as String?;
  String? get stage => data['stage'] as String?;

  /// 构造客户端 → 服务端的审批回执。
  ///
  /// 客户端按任务约定回发：`{"type":"approval","data":{"approval_id":...,"approved":...}}`。
  static String buildApproval(String approvalId, bool approved) {
    return jsonEncode({
      'type': 'approval',
      'data': {'approval_id': approvalId, 'approved': approved},
    });
  }
}
