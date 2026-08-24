import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../models/knowledge_card.dart';
import '../models/offline_pack.dart';
import '../services/offline_pack_service.dart';

class QuizPage extends ConsumerStatefulWidget {
  const QuizPage({super.key});

  @override
  ConsumerState<QuizPage> createState() => _QuizPageState();
}

class _QuizPageState extends ConsumerState<QuizPage> {
  List<KnowledgeCard> _cards = const [];
  String? _selectedCardId;
  List<QuizQuestion> _questions = const [];
  final _answers = <String, TextEditingController>{};
  bool _loadingCards = true;
  bool _loadingQuiz = false;
  Map<String, dynamic>? _result;

  @override
  void initState() {
    super.initState();
    _loadCards();
  }

  @override
  void dispose() {
    for (final controller in _answers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadCards() async {
    try {
      final cards = await ref.read(apiClientProvider).listCards(limit: 200);
      if (!mounted) return;
      setState(() {
        _cards = cards;
        _loadingCards = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loadingCards = false);
    }
  }

  Future<void> _generate() async {
    final cardId = _selectedCardId;
    if (cardId == null) return;
    setState(() => _loadingQuiz = true);
    try {
      final questions =
          await ref.read(apiClientProvider).generateQuiz(cardId);
      if (!mounted) return;
      for (final controller in _answers.values) {
        controller.dispose();
      }
      _answers.clear();
      setState(() {
        _questions = questions;
        _result = null;
        _loadingQuiz = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loadingQuiz = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('生成失败: $e')),
      );
    }
  }

  Future<void> _grade() async {
    final cardId = _selectedCardId;
    if (cardId == null || _questions.isEmpty) return;
    final answers = _questions.map((q) {
      return {
        'question': q.question,
        'answer': _answers[q.question]?.text.trim() ?? '',
      };
    }).toList();
    setState(() => _loadingQuiz = true);
    try {
      final result =
          await ref.read(apiClientProvider).gradeQuiz(
                cardId: cardId,
                answers: answers,
              );
      if (!mounted) return;
      setState(() {
        _result = result;
        _loadingQuiz = false;
      });
      // 网络已恢复：尝试回传离线队列中的历史评分。
      _flushOfflineQueue();
    } catch (e) {
      if (!mounted) return;
      setState(() => _loadingQuiz = false);
      // 离线作答：结果进入待回传队列，网络恢复后批量 POST /api/quiz/grade。
      await ref.read(offlinePackServiceProvider).enqueueGrade(
            QuizGradeRequest(
              cardId: cardId,
              answers: answers,
              submittedAt: DateTime.now().toUtc().toIso8601String(),
            ),
          );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('离线保存，待网络恢复后回传（$e）')),
      );
    }
  }

  Future<void> _flushOfflineQueue() async {
    final service = ref.read(offlinePackServiceProvider);
    final result = await service.flushPendingGrades();
    if (!mounted) return;
    if (result.sent > 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('已回传 ${result.sent} 条离线评分')),
      );
    }
  }

  TextEditingController _controllerFor(QuizQuestion question) {
    return _answers.putIfAbsent(question.question, TextEditingController.new);
  }

  @override
  Widget build(BuildContext context) {
    if (_loadingCards) {
      return const Center(child: CircularProgressIndicator());
    }
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          DropdownButtonFormField<String>(
            value: _selectedCardId,
            decoration: const InputDecoration(labelText: '选择卡片'),
            items: _cards
                .map(
                  (c) => DropdownMenuItem(value: c.id, child: Text(c.title)),
                )
                .toList(),
            onChanged: (value) {
              setState(() {
                _selectedCardId = value;
                _questions = const [];
                _result = null;
              });
            },
          ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: _selectedCardId == null || _loadingQuiz
                ? null
                : _generate,
            child: Text(_loadingQuiz ? '生成中...' : '生成 Quiz'),
          ),
          const SizedBox(height: 16),
          Expanded(child: _buildBody()),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_result != null) {
      final results = _result!['results'];
      final total = _result!['total_score'];
      final max = _result!['max_score'];
      return ListView(
        children: [
          Text(
            '得分: $total / $max',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          if (results is List)
            ...results.map(
              (r) => Card(
                child: ListTile(
                  title: Text(r['comment']?.toString() ?? ''),
                  subtitle: Text(
                    '${r['score'] ?? 0} 分 · ${r['reference'] ?? ''}',
                  ),
                ),
              ),
            ),
        ],
      );
    }
    if (_questions.isEmpty) {
      return const Center(child: Text('选择卡片并生成题目'));
    }
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            itemCount: _questions.length,
            itemBuilder: (context, index) {
              final question = _questions[index];
              final controller = _controllerFor(question);
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Q${index + 1}. ${question.question}',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      const SizedBox(height: 6),
                      TextField(
                        controller: controller,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          hintText: '输入你的答案',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: _loadingQuiz
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(8),
                    child: CircularProgressIndicator(),
                  ),
                )
              : FilledButton.icon(
                  onPressed: _grade,
                  icon: const Icon(Icons.grade),
                  label: const Text('提交评分'),
                ),
        ),
      ],
    );
  }
}
