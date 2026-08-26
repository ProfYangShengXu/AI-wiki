import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../models/quiz_card.dart';
import '../theme/glass_theme.dart';

/// Quiz 卡片详情页 — 查看/编辑题目、作答、提交评分、查看评分。
class QuizDetailPage extends ConsumerStatefulWidget {
  const QuizDetailPage({
    super.key,
    required this.quiz,
    this.cardTitle,
    this.onChanged,
  });

  final QuizCard quiz;

  /// 关联知识卡片标题(列表页传入, 免二次加载)。
  final String? cardTitle;

  /// 内容变化(保存/评分/删除)后通知列表页刷新。
  final VoidCallback? onChanged;

  @override
  ConsumerState<QuizDetailPage> createState() => _QuizDetailPageState();
}

class _QuizDetailPageState extends ConsumerState<QuizDetailPage> {
  late QuizCard _quiz = widget.quiz;
  late final List<TextEditingController> _questionCtrls;
  late final List<TextEditingController> _refCtrls;
  late final List<TextEditingController> _answerCtrls;
  bool _editMode = false;
  bool _showRef = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _initCtrls(_quiz.questions);
  }

  void _initCtrls(List<QuizQuestionItem> questions) {
    _questionCtrls = [
      for (final q in questions) TextEditingController(text: q.question),
    ];
    _refCtrls = [
      for (final q in questions) TextEditingController(text: q.refAnswer),
    ];
    _answerCtrls = [
      for (final q in questions) TextEditingController(text: q.userAnswer),
    ];
  }

  @override
  void dispose() {
    for (final c in [..._questionCtrls, ..._refCtrls, ..._answerCtrls]) {
      c.dispose();
    }
    super.dispose();
  }

  void _disposeCtrls() {
    for (final c in [..._questionCtrls, ..._refCtrls, ..._answerCtrls]) {
      c.dispose();
    }
  }

  List<Map<String, dynamic>> _buildQuestions({bool withAnswers = false}) {
    return [
      for (var i = 0; i < _questionCtrls.length; i++)
        {
          'question': _questionCtrls[i].text.trim(),
          'ref_answer': _refCtrls[i].text.trim(),
          if (withAnswers) 'user_answer': _answerCtrls[i].text.trim(),
        },
    ];
  }

  Future<void> _saveDraft() async {
    final questions = _buildQuestions(withAnswers: true);
    if (questions.any((q) => (q['question'] as String).isEmpty)) {
      _snack('题目不能为空');
      return;
    }
    setState(() => _busy = true);
    try {
      final updated = await ref.read(apiClientProvider).updateQuiz(
            _quiz.id,
            questions: questions,
            userEdited: true,
            status: 'draft',
            submitted: false,
          );
      if (!mounted) return;
      setState(() {
        _quiz = updated;
        _editMode = false;
        _busy = false;
      });
      _syncCtrls(updated.questions);
      widget.onChanged?.call();
      _snack('草稿已保存');
    } catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      _snack('保存失败: $e');
    }
  }

  Future<void> _grade() async {
    final answers = [
      for (var i = 0; i < _questionCtrls.length; i++)
        {
          'question': _questionCtrls[i].text.trim(),
          'answer': _answerCtrls[i].text.trim(),
        },
    ];
    if (answers.any((a) => (a['answer'] as String).isEmpty)) {
      _snack('请先填写所有答案');
      return;
    }
    setState(() => _busy = true);
    try {
      final cardId = _quiz.cardIds.isNotEmpty ? _quiz.cardIds.first : '';
      await ref.read(apiClientProvider).gradeQuiz(
            cardId: cardId,
            quizId: _quiz.id,
            answers: answers,
          );
      final refreshed = await ref.read(apiClientProvider).getQuiz(_quiz.id);
      if (!mounted) return;
      setState(() {
        _quiz = refreshed;
        _busy = false;
      });
      _syncCtrls(refreshed.questions);
      widget.onChanged?.call();
      _snack('评分完成');
    } catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      _snack('评分失败: $e');
    }
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除 Quiz'),
        content: Text('确定删除「${_quiz.title}」吗？'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('删除')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await ref.read(apiClientProvider).deleteQuiz(_quiz.id);
      widget.onChanged?.call();
      if (mounted) Navigator.pop(context);
    } catch (e) {
      _snack('删除失败: $e');
    }
  }

  void _syncCtrls(List<QuizQuestionItem> questions) {
    _disposeCtrls();
    _initCtrls(questions);
  }

  void _snack(String msg) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(_quiz.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        actions: [
          if (!_quiz.graded)
            IconButton(
              tooltip: '编辑题目',
              onPressed: () => setState(() => _editMode = !_editMode),
              icon: Icon(_editMode ? Icons.check : Icons.edit_outlined),
            ),
          IconButton(
            tooltip: '删除',
            onPressed: _busy ? null : _delete,
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
      body: GlassTheme.background(
        context,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildHeader(theme),
            Expanded(child: _buildQuestionsList(theme)),
            _buildBottomBar(theme),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      child: GlassTheme.glassTile(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        radius: const BorderRadius.all(Radius.circular(14)),
        child: Row(
          children: [
            _StatusChip(status: _quiz.status, graded: _quiz.graded),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (widget.cardTitle != null && widget.cardTitle!.isNotEmpty)
                    Text(
                      '关联: ${widget.cardTitle}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall,
                    ),
                  Text(
                    '创建: ${_fmtTime(_quiz.createdAt)}'
                    '${_quiz.userEdited ? ' · 用户已编辑' : ''}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
            IconButton(
              tooltip: '显示/隐藏参考答案',
              onPressed: () => setState(() => _showRef = !_showRef),
              icon: Icon(
                _showRef ? Icons.visibility : Icons.visibility_off_outlined,
                size: 20,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuestionsList(ThemeData theme) {
    final questions = _quiz.questions;
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      itemCount: questions.length,
      itemBuilder: (context, index) {
        final q = questions[index];
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: GlassTheme.glassTile(
            padding: const EdgeInsets.all(12),
            radius: const BorderRadius.all(Radius.circular(14)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Q${index + 1}. ${q.question}',
                  style: theme.textTheme.titleSmall,
                ),
                if (_editMode) ...[
                  const SizedBox(height: 6),
                  TextField(
                    controller: _questionCtrls[index],
                    maxLines: 2,
                    decoration: const InputDecoration(
                      labelText: '题目',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    controller: _refCtrls[index],
                    maxLines: 2,
                    decoration: const InputDecoration(
                      labelText: '参考答案',
                      border: OutlineInputBorder(),
                    ),
                  ),
                ] else if (_showRef && q.refAnswer.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    '参考答案: ${q.refAnswer}',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.primary),
                  ),
                ],
                const SizedBox(height: 6),
                TextField(
                  controller: _answerCtrls[index],
                  maxLines: 3,
                  enabled: !_quiz.graded,
                  decoration: InputDecoration(
                    hintText: '输入你的答案',
                    border: const OutlineInputBorder(),
                    labelText: q.graded ? '我的答案(${q.score} 分)' : '我的答案',
                  ),
                ),
                if (q.graded && q.comment.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    '点评: ${q.comment}',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildBottomBar(ThemeData theme) {
    if (_busy) {
      return const Padding(
        padding: EdgeInsets.all(12),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    final graded = _quiz.graded;
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          if (graded)
            Expanded(
              child: GlassTheme.glassTile(
                padding: const EdgeInsets.symmetric(vertical: 10),
                radius: const BorderRadius.all(Radius.circular(14)),
                child: Center(
                  child: Text(
                    '得分: ${_quiz.totalScore} / ${_quiz.maxScore}',
                    style: theme.textTheme.titleMedium,
                  ),
                ),
              ),
            )
          else ...[
            Expanded(
              child: OutlinedButton(
                onPressed: _saveDraft,
                child: const Text('保存草稿'),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: FilledButton.icon(
                onPressed: _grade,
                icon: const Icon(Icons.grade, size: 18),
                label: const Text('提交评分'),
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _fmtTime(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      String two(int v) => v.toString().padLeft(2, '0');
      return '${dt.year}-${two(dt.month)}-${two(dt.day)} '
          '${two(dt.hour)}:${two(dt.minute)}';
    } catch (_) {
      return iso;
    }
  }
}

/// 状态徽章: 未提交 / 已提交 / 已评分。
class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status, required this.graded});

  final String status;
  final bool graded;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (label, color) = switch ((status, graded)) {
      ('graded', _) => ('已评分', const Color(0xFF16A34A)),
      ('submitted', _) => ('已提交', theme.colorScheme.primary),
      _ => ('未提交', theme.colorScheme.onSurfaceVariant),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.5), width: 0.5),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
