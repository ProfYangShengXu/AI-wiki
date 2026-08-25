import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/api_client.dart';
import '../models/ws_event.dart';
import '../services/app_logger.dart';
import '../state/refresh.dart';
import '../theme/glass_theme.dart';
import '../widgets/markdown_text.dart';

class _ToolStep {
  const _ToolStep({
    required this.tool,
    this.summary = '',
    this.ok = false,
    this.running = false,
  });

  final String tool;
  final String summary;
  final bool ok;
  final bool running;
}

class _ChatItem {
  const _ChatItem({
    required this.role,
    this.text = '',
    this.toolSteps = const [],
    this.streaming = false,
  });

  final String role;
  final String text;
  final List<_ToolStep> toolSteps;
  final bool streaming;

  _ChatItem copyWith({
    String? text,
    List<_ToolStep>? toolSteps,
    bool? streaming,
  }) {
    return _ChatItem(
      role: role,
      text: text ?? this.text,
      toolSteps: toolSteps ?? this.toolSteps,
      streaming: streaming ?? this.streaming,
    );
  }
}

/// 可复用对话面板: WebSocket 接入 Ask/Agent 双模式, 支持
/// - Markdown 渲染 (MarkdownText)
/// - 知识库卡片标题链接跳转 (onCardTap)
/// - 文件选择自动导入 (file picker → 上传 → 后端自动解析)
/// - 窄宽度紧凑模式 (showModeToggle=false 时隐藏模式切换)
class ChatPanel extends ConsumerStatefulWidget {
  const ChatPanel({
    super.key,
    this.showModeToggle = true,
    this.cardTitles = const {},
    this.onCardTap,
  });

  final bool showModeToggle;
  final Set<String> cardTitles;
  final void Function(String title)? onCardTap;

  @override
  ConsumerState<ChatPanel> createState() => _ChatPanelState();
}

class _ChatPanelState extends ConsumerState<ChatPanel> {
  final _controller = TextEditingController();
  final _messages = <_ChatItem>[];
  WebSocketChannel? _channel;
  String _mode = 'ask';
  String _sessionStatus = '';
  int _currentAssistant = -1;
  bool _uploading = false;

  @override
  void initState() {
    super.initState();
    _connect();
  }

  void _connect() {
    final url = ref.read(apiClientProvider).wsUrl('/ws/chat');
    try {
      final channel = WebSocketChannel.connect(Uri.parse(url));
      _channel = channel;
      channel.stream.listen(
        _onEvent,
        onError: (_) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('对话连接中断，请稍后重试')),
            );
          }
        },
        onDone: () => _channel = null,
      );
    } catch (_) {
      // 后端未连接时由 bootstrap gate 先行处理。
    }
  }

  void _onEvent(dynamic raw) {
    final event = WsEvent.parse(raw as String);
    if (event == null || !mounted) return;

    switch (event.type) {
      case WsEvent.typeSessionStarted:
        setState(() {
          _sessionStatus = '处理中';
          _currentAssistant = -1;
        });
        break;
      case WsEvent.typeLlmDelta:
        _appendDelta(event.delta ?? '');
        break;
      case WsEvent.typeToolCalled:
        _addToolStep(event.tool ?? 'unknown', running: true);
        break;
      case WsEvent.typeToolResult:
        _finishToolStep(
          event.tool ?? 'unknown',
          summary: event.toolSummary ?? '',
          ok: event.toolOk,
        );
        break;
      case WsEvent.typeApprovalRequired:
        _handleApproval(event);
        break;
      case WsEvent.typeSessionDone:
        setState(() {
          _sessionStatus = '完成';
          _finalizeAssistant();
        });
        break;
      case WsEvent.typeSessionError:
        setState(() {
          _sessionStatus = '出错';
          _finalizeAssistant();
        });
        break;
      case WsEvent.typeResponse:
        setState(() {
          _messages.add(_ChatItem(role: 'assistant', text: event.content));
        });
        break;
      case WsEvent.typeProgress:
        setState(() => _sessionStatus = event.stage ?? '');
        break;
      case WsEvent.typeError:
        setState(() {
          _messages.add(
            _ChatItem(
              role: 'system',
              text: event.content.isNotEmpty ? event.content : '对话出错',
            ),
          );
        });
        break;
      default:
        break;
    }
  }

  void _appendDelta(String delta) {
    if (delta.isEmpty) return;
    setState(() {
      if (_currentAssistant < 0 || _currentAssistant >= _messages.length) {
        _messages.add(_ChatItem(role: 'assistant', text: delta, streaming: true));
        _currentAssistant = _messages.length - 1;
      } else {
        final item = _messages[_currentAssistant];
        _messages[_currentAssistant] =
            item.copyWith(text: item.text + delta, streaming: true);
      }
    });
  }

  _ChatItem _ensureAssistant() {
    if (_currentAssistant >= 0 && _currentAssistant < _messages.length) {
      return _messages[_currentAssistant];
    }
    const item = _ChatItem(role: 'assistant', streaming: true);
    _messages.add(item);
    _currentAssistant = _messages.length - 1;
    return item;
  }

  void _addToolStep(String tool, {required bool running}) {
    setState(() {
      final item = _ensureAssistant();
      final steps = List<_ToolStep>.from(item.toolSteps)
        ..add(_ToolStep(tool: tool, running: running));
      _messages[_currentAssistant] = item.copyWith(toolSteps: steps);
    });
  }

  void _finishToolStep(String tool, {required String summary, required bool ok}) {
    setState(() {
      if (_currentAssistant < 0 || _currentAssistant >= _messages.length) return;
      final item = _messages[_currentAssistant];
      final steps = item.toolSteps
          .map((s) => s.tool == tool
              ? _ToolStep(tool: s.tool, summary: summary, ok: ok, running: false)
              : s)
          .toList();
      _messages[_currentAssistant] = item.copyWith(toolSteps: steps);
    });
  }

  void _finalizeAssistant() {
    if (_currentAssistant < 0 || _currentAssistant >= _messages.length) return;
    final item = _messages[_currentAssistant];
    _messages[_currentAssistant] = item.copyWith(streaming: false);
    _currentAssistant = -1;
  }

  Future<void> _handleApproval(WsEvent event) async {
    final approvalId = event.approvalId;
    if (approvalId == null || !mounted) return;
    final approved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('需要确认'),
        content: Text('工具「${event.tool ?? '未知'}」请求执行，是否允许？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('拒绝'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('允许'),
          ),
        ],
      ),
    );
    final channel = _channel;
    if (channel != null && approved != null) {
      channel.sink.add(WsEvent.buildApproval(approvalId, approved));
    }
  }

  /// 文件选择 → 上传 → 后端自动解析导入。
  Future<void> _pickAndUpload() async {
    if (_uploading) return;
    FilePickerResult? result;
    try {
      result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: const ['pdf', 'doc', 'docx', 'md', 'txt', 'pptx', 'ppt'],
      );
    } catch (_) {
      result = null;
    }
    if (result == null || result.files.isEmpty) return;
    final file = result.files.single;
    if (file.path == null || file.path!.isEmpty) return;

    setState(() => _uploading = true);
    try {
      final api = ref.read(apiClientProvider);
      final info = await api.uploadDocument(File(file.path!));
      final taskId = info['task_id']?.toString() ?? '';
      if (!mounted) return;
      setState(() {
        _messages.add(_ChatItem(
          role: 'user',
          text: '📎 导入文件: ${file.name}（已上传，正在解析…）',
        ));
      });
      // 轮询导入任务, 完成后通知知识库刷新
      if (taskId.isNotEmpty) {
        _pollTask(taskId, file.name);
      }
      // 提示后端开始解析 (Agent 模式接管后续状态事件)
      _channel?.sink.add(
        jsonEncode({
          'type': 'message',
          'content': '我已上传文件「${file.name}」，请解析并导入知识库，完成后简要总结。',
          'data': {'mode': 'agent'},
        }),
      );
    } catch (e, st) {
      if (!mounted) return;
      try {
        AppLogger.log('聊天导入异常: $e\n$st');
      } catch (_) {}
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('上传失败: $e')),
      );
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _pollTask(String taskId, String fileName) async {
    final api = ref.read(apiClientProvider);
    for (var i = 0; i < 600; i++) {
      await Future<void>.delayed(const Duration(seconds: 1));
      if (!mounted || _channel == null) return;
      try {
        final st = await api.uploadTaskStatus(taskId);
        final status = st['status'] as String? ?? '';
        if (status == 'done' || status == 'failed' || status == 'cancelled') {
          // 导入结束 → 通知知识库列表刷新
          ref.read(dataRefreshProvider.notifier).state++;
          if (mounted) {
            setState(() {
              _messages.add(_ChatItem(
                role: 'system',
                text: status == 'done'
                    ? '✅ 「$fileName」导入完成'
                    : '⚠️ 「$fileName」导入${status == 'failed' ? '失败' : '已取消'}',
              ));
            });
          }
          return;
        }
      } catch (_) {
        // 轮询失败继续重试
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _channel?.sink.close();
    super.dispose();
  }

  void _send() {
    final text = _controller.text.trim();
    if (text.isEmpty || _channel == null) return;
    setState(() {
      _messages.add(_ChatItem(role: 'user', text: text));
    });
    _channel?.sink.add(
      jsonEncode({
        'type': 'message',
        'content': text,
        'data': {'mode': _mode},
      }),
    );
    _controller.clear();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (widget.showModeToggle)
          Padding(
            padding: const EdgeInsets.all(8),
            // 模式切换器: 毛玻璃浮层(用户指定的半透明组件场景)
            child: GlassTheme.glassCard(
              padding: const EdgeInsets.all(4),
              radius: const BorderRadius.all(Radius.circular(12)),
              blur: 20,
              opacity: 0.5,
              child: SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'ask', label: Text('Ask')),
                  ButtonSegment(value: 'agent', label: Text('Agent')),
                ],
                selected: {_mode},
                onSelectionChanged: (values) =>
                    setState(() => _mode = values.first),
              ),
            ),
          ),
        Expanded(
          child: _messages.isEmpty
              ? ListView(
                  padding: const EdgeInsets.all(12),
                  children: const [
                    Text('与 Agent 对话: 提问、让我导入文件、修改卡片等。'),
                  ],
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(12),
                  itemCount: _messages.length,
                  itemBuilder: (context, index) =>
                      _buildItem(_messages[index]),
                ),
        ),
        if (_sessionStatus.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                _sessionStatus,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.all(8),
          child: Row(
            children: [
              IconButton(
                tooltip: '选择文件自动导入',
                onPressed: _uploading ? null : _pickAndUpload,
                icon: _uploading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.attach_file),
              ),
              Expanded(
                child: TextField(
                  controller: _controller,
                  decoration: const InputDecoration(
                    hintText: '输入问题或指令',
                    border: OutlineInputBorder(),
                  ),
                  onSubmitted: (_) => _send(),
                ),
              ),
              const SizedBox(width: 8),
              SpringPress(
                onTap: _send,
                child: FilledButton(onPressed: _send, child: const Text('发送')),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildItem(_ChatItem item) {
    final theme = Theme.of(context);
    if (item.role == 'system') {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Text(
          item.text,
          textAlign: TextAlign.center,
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.error),
        ),
      );
    }
    final isUser = item.role == 'user';
    final bubbleContent = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (item.text.isNotEmpty)
          isUser
              ? Text(
                  item.text,
                  style: TextStyle(color: theme.colorScheme.onPrimary),
                )
              : MarkdownText(
                  item.text,
                  cardTitles: widget.cardTitles,
                  onCardTap: widget.onCardTap,
                  style: TextStyle(color: theme.colorScheme.onSurface),
                ),
        if (item.streaming)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              '…',
              style: TextStyle(color: theme.colorScheme.onSurface),
            ),
          ),
        if (item.toolSteps.isNotEmpty) ...[
          const SizedBox(height: 6),
          ...item.toolSteps.map((step) => _buildToolStep(step)),
        ],
      ],
    );
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: isUser
          ? Container(
              margin: const EdgeInsets.symmetric(vertical: 4),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              constraints: const BoxConstraints(maxWidth: 560),
              decoration: BoxDecoration(
                color: theme.colorScheme.primary,
                borderRadius: BorderRadius.circular(14),
              ),
              child: bubbleContent,
            )
          : GlassTheme.glassTile(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              radius: const BorderRadius.all(Radius.circular(14)),
              opacity: 0.5,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: bubbleContent,
              ),
            ),
    );
  }

  Widget _buildToolStep(_ToolStep step) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(top: 4),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        children: [
          if (step.running)
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else
            Icon(
              step.ok ? Icons.check_circle_outline : Icons.error_outline,
              size: 16,
              color: step.ok ? Colors.green : theme.colorScheme.error,
            ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              step.summary.isEmpty ? step.tool : '${step.tool}: ${step.summary}',
              style: theme.textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}
