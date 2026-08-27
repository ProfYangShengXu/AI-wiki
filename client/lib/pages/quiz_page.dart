import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../models/knowledge_card.dart';
import '../models/quiz_card.dart';
import '../theme/glass_theme.dart';
import '../widgets/app_snackbar.dart';
import 'quiz_detail_page.dart';

/// Quiz 页 — 关键词搜索知识卡片(按重合度排序)生成 Quiz + 已保存 quiz 卡片列表。
class QuizPage extends ConsumerStatefulWidget {
  const QuizPage({super.key});

  @override
  ConsumerState<QuizPage> createState() => _QuizPageState();
}

class _QuizPageState extends ConsumerState<QuizPage> {
  final _searchCtrl = TextEditingController();
  Timer? _debounce;
  KnowledgeCard? _selectedCard;
  List<KnowledgeCard> _searchResults = const [];
  bool _searching = false;
  bool _showDropdown = false;

  List<QuizCard> _quizzes = const [];
  bool _loadingQuizzes = true;
  bool _generating = false;
  Map<String, String> _cardTitles = const {};

  @override
  void initState() {
    super.initState();
    _loadQuizzes();
    _loadCardTitles();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadCardTitles() async {
    try {
      final cards = await ref.read(apiClientProvider).listCards(limit: 200);
      if (!mounted) return;
      setState(() {
        _cardTitles = {for (final c in cards) c.id: c.title};
      });
    } catch (_) {
      // 标题映射失败不阻断主流程。
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

  // ── 关键词搜索(重合度排序) ────────────────────────────

  void _onSearchChanged(String text) {
    _debounce?.cancel();
    final q = text.trim();
    if (q.isEmpty) {
      setState(() {
        _searchResults = const [];
        _showDropdown = false;
        _searching = false;
        if (_selectedCard != null) {
          // 清空输入时保留已选卡片, 但回退显示其标题
          _searchCtrl.text = _selectedCard!.title;
        }
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 300), () => _search(q));
  }

  Future<void> _search(String q) async {
    setState(() {
      _searching = true;
      _showDropdown = true;
    });
    try {
      final results = await ref.read(apiClientProvider).searchCards(q);
      if (!mounted || _searchCtrl.text.trim() != q) return;
      setState(() {
        _searchResults = results;
        _searching = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _searchResults = const [];
        _searching = false;
      });
    }
  }

  void _selectCard(KnowledgeCard card) {
    setState(() {
      _selectedCard = card;
      _searchCtrl.text = card.title;
      _showDropdown = false;
      _searchResults = const [];
    });
  }

  /// 生成 Quiz(后端保存为 quiz 卡片) → 刷新列表并打开详情。
  Future<void> _generate() async {
    final card = _selectedCard;
    if (card == null) return;
    setState(() => _generating = true);
    try {
      final result = await ref.read(apiClientProvider).generateQuiz(card.id);
      if (!mounted) return;
      setState(() => _generating = false);
      await _loadQuizzes();
      if (!mounted) return;
      QuizCard? created;
      if (result.quizId.isNotEmpty) {
        for (final q in _quizzes) {
          if (q.id == result.quizId) {
            created = q;
            break;
          }
        }
      }
      created ??= _quizzes.isNotEmpty ? _quizzes.first : null;
      if (created != null) _openDetail(created);
    } catch (e) {
      if (!mounted) return;
      setState(() => _generating = false);
      AppSnack.error(context, '生成失败: $e');
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

  /// ① 删除 quiz 卡片(列表页入口)。
  Future<void> _deleteQuiz(QuizCard quiz) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除 Quiz'),
        content: Text('确定删除「${quiz.title}」吗？'),
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
      await ref.read(apiClientProvider).deleteQuiz(quiz.id);
      _loadQuizzes();
    } catch (e) {
      if (mounted) {
        AppSnack.error(context, '删除失败: $e');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 关键词搜索 + 生成(生成即保存为 quiz 卡片)
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: _buildSearchArea()),
              const SizedBox(width: 8),
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: FilledButton(
                  onPressed: _selectedCard == null || _generating
                      ? null
                      : _generate,
                  child: Text(_generating ? '生成中...' : '生成 Quiz'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
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

  /// 搜索框 + 重合度排序下拉。
  Widget _buildSearchArea() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _searchCtrl,
          onChanged: _onSearchChanged,
          onTap: () {
            if (_selectedCard != null && _searchCtrl.text.isNotEmpty) {
              _searchCtrl.clear();
            }
          },
          decoration: InputDecoration(
            hintText: '输入关键词搜索知识卡片',
            prefixIcon: const Icon(Icons.search, size: 20),
            isDense: true,
            suffixIcon: _selectedCard != null
                ? IconButton(
                    icon: const Icon(Icons.clear, size: 18),
                    tooltip: '清除选择',
                    onPressed: () {
                      setState(() {
                        _selectedCard = null;
                        _searchCtrl.clear();
                        _showDropdown = false;
                      });
                    },
                  )
                : null,
          ),
        ),
        if (_showDropdown) _buildDropdown(),
      ],
    );
  }

  /// 重合度排序的下拉列表(后端混合检索已按相关度排序)。
  Widget _buildDropdown() {
    return Container(
      margin: const EdgeInsets.only(top: 4),
      constraints: const BoxConstraints(maxHeight: 260),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Theme.of(context).colorScheme.outlineVariant,
          width: 0.5,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: _searching
          ? const Padding(
              padding: EdgeInsets.all(12),
              child: Center(child: CircularProgressIndicator()),
            )
          : _searchResults.isEmpty
              ? const Padding(
                  padding: EdgeInsets.all(12),
                  child: Center(child: Text('无匹配卡片')),
                )
              : ListView.builder(
                  shrinkWrap: true,
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  itemCount: _searchResults.length > 8 ? 8 : _searchResults.length,
                  itemBuilder: (context, index) {
                    final card = _searchResults[index];
                    final highlighted = _selectedCard?.id == card.id;
                    return ListTile(
                      dense: true,
                      title: Text(
                        '${index + 1}. ${card.title}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontWeight:
                              highlighted ? FontWeight.w700 : FontWeight.w500,
                          color: highlighted
                              ? Theme.of(context).colorScheme.primary
                              : null,
                        ),
                      ),
                      subtitle: Text(
                        card.category,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      onTap: () => _selectCard(card),
                    );
                  },
                ),
    );
  }

  Widget _buildList() {
    if (_loadingQuizzes) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_quizzes.isEmpty) {
      return const Center(child: Text('暂无 Quiz,搜索卡片生成一份'));
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
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _StatusChip(status: quiz.status, graded: quiz.graded),
                  const SizedBox(width: 4),
                  IconButton(
                    tooltip: '删除',
                    icon: const Icon(Icons.delete_outline, size: 20),
                    onPressed: () => _deleteQuiz(quiz),
                  ),
                ],
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
