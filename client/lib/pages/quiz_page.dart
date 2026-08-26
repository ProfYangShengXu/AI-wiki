import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../models/knowledge_card.dart';
import '../models/quiz_card.dart';
import '../theme/glass_theme.dart';
import 'quiz_detail_page.dart';

/// Quiz 页 — 生成 Quiz(自动保存为 quiz 卡片) + 已保存 quiz 卡片列表。
class QuizPage extends ConsumerStatefulWidget {
  const QuizPage({super.key});

  @override
  ConsumerState<QuizPage> createState() => _QuizPageState();
}

class _QuizPageState extends ConsumerState<QuizPage> {
  List<KnowledgeCard> _cards = const [];
  String? _selectedCardId;
  List<QuizCard> _quizzes = const [];
  bool _loadingCards = true;
  bool _loadingQuizzes = true;
  bool _generating = false;
  Map<String, String> _cardTitles = const {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    await Future.wait([_loadCards(), _loadQuizzes()]);
  }

  Future<void> _loadCards() async {
    try {
      final cards = await ref.read(apiClientProvider).listCards(limit: 200);
      if (!mounted) return;
      setState(() {
        _cards = cards;
        _cardTitles = {for (final c in cards) c.id: c.title};
        _loadingCards = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadingCards = false);
    }
  }

  Future<void> _loadQuizzes() async {
    try {
      final quizzes = await ref.read(apiClientProvider).listQuizzes();
      if (!mounted) return;
      setState(() {
        _quizzes = quizzes;
        _loadingQuizzes = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadingQuizzes = false);
    }
  }

  /// 生成 Quiz(后端保存为 quiz 卡片) → 刷新列表并打开详情。
  Future<void> _generate() async {
    final cardId = _selectedCardId;
    if (cardId == null) return;
    setState(() => _generating = true);
    try {
      final result = await ref.read(apiClientProvider).generateQuiz(cardId);
      if (!mounted) return;
      setState(() => _generating = false);
      await _loadQuizzes();
      if (!mounted) return;
      // 用返回的 quiz_id 打开详情(后端已入库)
      final quizzes = _quizzes;
      QuizCard? created;
      if (result.quizId.isNotEmpty) {
        for (final q in quizzes) {
          if (q.id == result.quizId) {
            created = q;
            break;
          }
        }
      }
      created ??= quizzes.isNotEmpty ? quizzes.first : null;
      if (created != null) {
        _openDetail(created);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _generating = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('生成失败: $e')),
      );
    }
  }

  void _openDetail(QuizCard quiz) {
    final cardId = quiz.cardIds.isNotEmpty ? quiz.cardIds.first : '';
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => QuizDetailPage(
          quiz: quiz,
          cardTitle: _cardTitles[cardId] ?? '',
          onChanged: _loadQuizzes,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loadingCards && _loadingQuizzes) {
      return const Center(child: CircularProgressIndicator());
    }
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 卡片选择 + 生成(生成即保存为 quiz 卡片)
          Row(
            children: [
              Expanded(
                child: DropdownButton<String>(
                  value: _selectedCardId,
                  isExpanded: true,
                  underline: const SizedBox.shrink(),
                  hint: const Text('选择卡片'),
                  items: _cards
                      .map((c) =>
                          DropdownMenuItem(value: c.id, child: Text(c.title)))
                      .toList(),
                  onChanged: (value) {
                    setState(() => _selectedCardId = value);
                  },
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _selectedCardId == null || _generating
                    ? null
                    : _generate,
                child: Text(_generating ? '生成中...' : '生成 Quiz'),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '已保存的 Quiz 卡片',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Expanded(child: _buildList()),
        ],
      ),
    );
  }

  Widget _buildList() {
    if (_loadingQuizzes) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_quizzes.isEmpty) {
      return const Center(child: Text('暂无 Quiz,选择卡片生成一份'));
    }
    return ListView.builder(
      itemCount: _quizzes.length,
      itemBuilder: (context, index) {
        final quiz = _quizzes[index];
        final cardId = quiz.cardIds.isNotEmpty ? quiz.cardIds.first : '';
        final cardTitle = _cardTitles[cardId] ?? '';
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: GlassTheme.glassTile(
            padding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            radius: const BorderRadius.all(Radius.circular(14)),
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                quiz.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              subtitle: Text(
                '${cardTitle.isEmpty ? '' : '$cardTitle · '}'
                '${quiz.questions.length} 题 · ${_fmtTime(quiz.createdAt)}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: _StatusChip(
                status: quiz.status,
                graded: quiz.graded,
              ),
              onTap: () => _openDetail(quiz),
            ),
          ),
        );
      },
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

/// 状态徽章: 未提交 / 已提交 / 已评分(与详情页一致)。
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
