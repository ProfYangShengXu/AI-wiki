import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../models/knowledge_card.dart';

class WikiPage extends ConsumerStatefulWidget {
  const WikiPage({super.key});

  @override
  ConsumerState<WikiPage> createState() => _WikiPageState();
}

class _WikiPageState extends ConsumerState<WikiPage> {
  List<String> _categories = const [];
  List<KnowledgeCard> _cards = const [];
  String? _category;
  KnowledgeCard? _selected;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final categories = await api.listCategories();
      final cards = await api.listCards(category: _category, limit: 200);
      if (!mounted) return;
      setState(() {
        _categories = categories;
        _cards = cards;
        _category ??= (categories.isEmpty ? null : categories.first);
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _open(KnowledgeCard card) async {
    setState(() => _selected = card);
    try {
      final fresh = await ref.read(apiClientProvider).getCard(card.id);
      if (!mounted) return;
      setState(() => _selected = fresh);
    } catch (_) {
      // 列表数据仍可展示。
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('加载失败: $_error', textAlign: TextAlign.center),
            const SizedBox(height: 8),
            FilledButton(onPressed: _load, child: const Text('重试')),
          ],
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final cardList = _buildCardList();
        if (constraints.maxWidth < 700) {
          return _selected == null
              ? cardList
              : _buildDetail(_selected!, onBack: () => setState(() => _selected = null));
        }
        return Row(
          children: [
            SizedBox(width: 300, child: cardList),
            const VerticalDivider(width: 1),
            Expanded(
              child: _selected == null
                  ? const Center(child: Text('选择一张卡片'))
                  : _buildDetail(_selected!),
            ),
          ],
        );
      },
    );
  }

  Widget _buildCardList() {
    final filtered = _category == null
        ? _cards
        : _cards.where((c) => c.category == _category).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(8),
          child: DropdownButtonFormField<String?>(
            value: _category,
            decoration: const InputDecoration(labelText: '分类'),
            items: [
              const DropdownMenuItem<String?>(
                value: null,
                child: Text('全部分类'),
              ),
              ..._categories.map(
                (c) => DropdownMenuItem<String?>(value: c, child: Text(c)),
              ),
            ],
            onChanged: (value) {
              setState(() {
                _category = value;
                _selected = null;
              });
              _load();
            },
          ),
        ),
        Expanded(
          child: filtered.isEmpty
              ? const Center(child: Text('暂无卡片'))
              : ListView.builder(
                  itemCount: filtered.length,
                  itemBuilder: (context, index) {
                    final card = filtered[index];
                    return ListTile(
                      title: Text(card.title),
                      subtitle: Text(card.category),
                      selected: _selected?.id == card.id,
                      onTap: () => _open(card),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildDetail(KnowledgeCard card, {VoidCallback? onBack}) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (onBack != null)
            TextButton.icon(
              onPressed: onBack,
              icon: const Icon(Icons.arrow_back),
              label: const Text('返回'),
            ),
          Row(
            children: [
              Expanded(
                child: Text(
                  card.title,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ),
              Chip(label: Text(card.category)),
            ],
          ),
          if (card.aliases.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                card.aliases.join(' / '),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          const SizedBox(height: 12),
          Text(card.content.isEmpty ? '（暂无内容）' : card.content),
          if (card.examples.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('案例', style: Theme.of(context).textTheme.titleMedium),
            ...card.examples.map(
              (e) => Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('• $e'),
              ),
            ),
          ],
          if (card.questions.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('复习问题', style: Theme.of(context).textTheme.titleMedium),
            ...card.questions.map(
              (q) => Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('• $q'),
              ),
            ),
          ],
          if (card.sourceFile.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text(
              '来源: ${card.sourceFile} 第 ${card.sourcePage} 页',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }
}
