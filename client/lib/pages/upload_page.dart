import 'dart:async';
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

  /// 假进度 (0-1): 真实进度不可预测(取决于 AI 提取), 用缓慢推进的
  /// 假进度条给用户"正在生成"的确定感, 上限约 0.95, 完成后跳到 1。
  double _fakeProgress = 0;
  Timer? _fakeTicker;

  void _startFakeProgress() {
    // 防重复启动: 先停掉可能残留的旧 timer
    _fakeTicker?.cancel();
    _fakeProgress = 0;
    // 每 800ms 缓慢推进, 越接近 0.95 越慢, 营造"正在工作"感
    _fakeTicker = Timer.periodic(const Duration(milliseconds: 800), (_) {
      if (!mounted) return;
      setState(() {
        final remaining = 0.95 - _fakeProgress;
        _fakeProgress += (remaining * 0.12).clamp(0.004, 0.06);
      });
    });
  }

  void _stopFakeProgress({bool complete = false}) {
    _fakeTicker?.cancel();
    _fakeTicker = null;
    if (complete) {
      setState(() => _fakeProgress = 1.0);
    }
  }

  @override
  void dispose() {
    _fakeTicker?.cancel();
    super.dispose();
  }

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
        _status = '专属 Wiki 生成中';
        _progressText = '';
      });
      _startFakeProgress();
      if (taskId == null) {
        _stopFakeProgress();
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
    try {
      for (var i = 0; i < 120; i++) {
        await Future<void>.delayed(const Duration(seconds: 1));
        if (!mounted) return;
        try {
          final st = await api.uploadTaskStatus(taskId);
          final status = st['status'] as String? ?? '';
          setState(() {
            // 统一展示"专属 Wiki 生成中", 不暴露内部阶段数字
            if (status == 'done' || status == 'failed' || status == 'cancelled') {
              _status = _statusText(status);
            } else {
              _status = '专属 Wiki 生成中';
            }
            _progressText = '';
          });
          if (status == 'done' || status == 'failed' || status == 'cancelled') {
            _stopFakeProgress(complete: status == 'done');
            setState(() => _lastResult = st);
            // 导入完成/失败后通知知识库列表刷新
            ref.read(dataRefreshProvider.notifier).state++;
            // 明确提示: 成功/失败都弹 SnackBar
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                    status == 'done'
                        ? '✓ 导入完成: ${_lastResultText(st)}'
                        : '✗ 导入${status == 'failed' ? '失败' : '已取消'}',
                  ),
                  duration: const Duration(seconds: 4),
                ),
              );
            }
            return;
          }
        } catch (_) {
          // 轮询失败继续重试
        }
      }
    } finally {
      // 兜底: 轮询超时/异常退出时也停掉假进度 timer, 避免泄漏
      _stopFakeProgress();
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

  /// 完成结果的简短文案: 成功 X 张 · 跳过 Y 张 · 失败 Z 张。
  String _lastResultText(Map<String, dynamic> st) {
    final r = (st['result'] as Map?) ?? const {};
    final imported = r['imported'] ?? 0;
    final skipped = r['skipped'] ?? 0;
    final failed = r['failed'] ?? 0;
    if (imported == 0 && skipped == 0 && failed == 0) {
      return '无新卡片';
    }
    return '成功 $imported 张 · 跳过 $skipped 张 · 失败 $failed 张';
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
                if (_busy)
                  // 专属 Wiki 生成中: 转圈 + 文案 + 假进度条(带动画)
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 300),
                    child: Column(
                      key: const ValueKey('generating'),
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2.4),
                            ),
                            const SizedBox(width: 10),
                            Flexible(
                              child: Text(
                                _status,
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  fontWeight: FontWeight.w600,
                                  color: theme.colorScheme.primary,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        // 假进度条: 平滑推进到 _fakeProgress
                        TweenAnimationBuilder<double>(
                          tween: Tween(
                            begin: 0,
                            end: _fakeProgress,
                          ),
                          duration: const Duration(milliseconds: 700),
                          curve: Curves.easeOutCubic,
                          builder: (context, value, _) => ClipRRect(
                            borderRadius: BorderRadius.circular(4),
                            child: LinearProgressIndicator(
                              value: value,
                              minHeight: 6,
                              backgroundColor: theme.colorScheme.surfaceContainerHighest,
                            ),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'AI 正在提取知识点并生成专属 Wiki...',
                          style: theme.textTheme.bodySmall
                              ?.copyWith(color: theme.colorScheme.outline),
                        ),
                      ],
                    ),
                  )
                else
                  Text(_status, style: theme.textTheme.bodyMedium),
                if (_progressText.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('进度: $_progressText',
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.outline)),
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
          'AI 正在生成你的专属 Wiki，可随时取消。',
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
