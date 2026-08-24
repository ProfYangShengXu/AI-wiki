import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../services/app_logger.dart';
import '../state/refresh.dart';

/// 文档导入页: 选择文件 → 上传 → 实时轮询任务进度 → 展示结果。
class UploadPage extends ConsumerStatefulWidget {
  const UploadPage({super.key});

  @override
  ConsumerState<UploadPage> createState() => _UploadPageState();
}

class _UploadPageState extends ConsumerState<UploadPage> {
  bool _busy = false;
  String _status = '选择 PDF / Word / Markdown / TXT 文件导入知识库';
  Map<String, dynamic>? _lastResult;
  String _progressText = '';

  Future<void> _pickAndUpload() async {
    if (_busy) return;
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['pdf', 'doc', 'docx', 'md', 'txt'],
      allowMultiple: false,
    );
    final path = result?.files.single.path;
    if (path == null || path.isEmpty) return;
    setState(() {
      _busy = true;
      _status = '上传中...';
      _progressText = '';
      _lastResult = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final task = await api.uploadDocument(File(path));
      final taskId = task['task_id'] as String?;
      setState(() {
        _status = '上传成功，开始解析...';
      });
      if (taskId == null) {
        setState(() => _status = '上传失败: 未返回任务 ID');
        return;
      }
      await _poll(taskId);
    } catch (e, st) {
      // 记录完整异常(含堆栈)到客户端日志, 便于排查 Windows 端 OS 错误
      try {
        AppLogger.log('导入异常: $e\n$st');
      } catch (_) {}
      setState(() => _status = '上传失败: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _poll(String taskId) async {
    final api = ref.read(apiClientProvider);
    for (var i = 0; i < 120; i++) {
      await Future<void>.delayed(const Duration(seconds: 1));
      if (!mounted) return;
      try {
        final st = await api.uploadTaskStatus(taskId);
        final status = st['status'] as String? ?? '';
        final progress = (st['progress'] as Map?) ?? const {};
        final current = progress['current'] ?? '';
        final total = progress['total'] ?? '';
        setState(() {
          _status = _statusText(status);
          _progressText = '$current / $total';
        });
        if (status == 'done' || status == 'failed' || status == 'cancelled') {
          setState(() => _lastResult = st);
          // 导入完成/失败后通知知识库列表刷新
          ref.read(dataRefreshProvider.notifier).state++;
          return;
        }
      } catch (_) {
        // 轮询失败继续重试
      }
    }
  }

  String _statusText(String s) {
    switch (s) {
      case 'queued':
        return '排队中...';
      case 'scanning':
        return '扫描文档结构...';
      case 'extracting':
        return 'AI 提取知识点...';
      case 'linking':
        return '关联检测与入库...';
      case 'done':
        return '✓ 导入完成';
      case 'failed':
        return '✗ 导入失败';
      case 'cancelled':
        return '已取消';
      default:
        return s;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final result = _lastResult;
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.upload_file, color: theme.colorScheme.primary),
                    const SizedBox(width: 8),
                    Text('导入文档',
                        style: theme.textTheme.titleMedium),
                  ],
                ),
                const SizedBox(height: 12),
                Text(_status, style: theme.textTheme.bodyMedium),
                if (_progressText.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('进度: $_progressText',
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.outline)),
                ],
                if (_busy) ...[
                  const SizedBox(height: 12),
                  const LinearProgressIndicator(),
                ],
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: _busy ? null : _pickAndUpload,
                  icon: const Icon(Icons.add),
                  label: const Text('选择文件并导入'),
                ),
              ],
            ),
          ),
        ),
        if (result != null) _resultCard(context, result),
        const SizedBox(height: 12),
        Text(
          '支持的格式: PDF、Word(doc/docx)、Markdown、TXT。导入过程在本地完成，'
          'AI 提取进度会实时显示，可随时取消。',
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.outline),
        ),
      ],
    );
  }

  Widget _resultCard(BuildContext context, Map<String, dynamic> st) {
    final theme = Theme.of(context);
    final r = (st['result'] as Map?) ?? const {};
    final imported = r['imported'] ?? 0;
    final skipped = r['skipped'] ?? 0;
    final failed = r['failed'] ?? 0;
    final status = st['status'] as String? ?? '';
    final isDone = status == 'done';
    return Card(
      color: isDone ? null : theme.colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('导入结果', style: theme.textTheme.titleSmall),
            const SizedBox(height: 8),
            Text('成功 $imported 张 | 跳过 $skipped 张 | 失败 $failed 张'),
            if (status == 'failed')
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  '错误信息: ${st['message'] ?? ''}',
                  style: theme.textTheme.bodySmall,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
