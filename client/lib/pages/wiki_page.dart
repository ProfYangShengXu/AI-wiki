import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../models/knowledge_card.dart';
import '../state/refresh.dart';
import '../theme/glass_theme.dart';
import '../widgets/chat_panel.dart';
import '../widgets/markdown_text.dart';

class WikiPage extends ConsumerStatefulWidget {
  const WikiPage({super.key, this.reloadNotifier});

  /// HomeShell 切到知识库 tab 时递增, 触发强制刷新(双保险)。
  final ValueNotifier<int>? reloadNotifier;

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
    widget.reloadNotifier?.addListener(_onReloadSignal);
    _load();
  }

  @override
  void dispose() {
    widget.reloadNotifier?.removeListener(_onReloadSignal);
    super.dispose();
  }

  void _onReloadSignal() {
    if (mounted) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final categories = await api.listCategories();
      final cards = await api.listCards(
        category: _category,
        limit: 500,
        sort: 'source', // 按文件导入时间 + 页码排列
      );
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

  void _onCardLinked(String title) {
    // 从对话/详情链接跳转到对应卡片 (标题或别名)
    final match = _cards.where((c) =>
        c.title == title || c.aliases.contains(title)).toList();
    if (match.isNotEmpty) {
      _open(match.first);
    }
  }

  Set<String> get _cardTitles => {
        for (final c in _cards)
          ...{c.title, ...c.aliases},
      };

  Future<void> _editCard(KnowledgeCard card) async {
    final updated = await _showCardEditor(card);
    if (updated == null || !mounted) return;
    try {
      await ref.read(apiClientProvider).updateCard(card.id, updated);
      ref.read(dataRefreshProvider.notifier).state++;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('卡片已更新')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('更新失败: $e')),
        );
      }
    }
  }

  Future<void> _createCard() async {
    final created = await _showCardEditor(null);
    if (created == null || !mounted) return;
    try {
      final api = ref.read(apiClientProvider);
      final card = await api.createCard({
        ...created,
        'category': created['category'] ?? '通用',
      });
      ref.read(dataRefreshProvider.notifier).state++;
      if (mounted) {
        _open(card);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('创建失败: $e')),
        );
      }
    }
  }

  Future<void> _deleteCard(KnowledgeCard card) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除卡片'),
        content: Text('确定删除「${card.title}」吗？此操作不可撤销。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await ref.read(apiClientProvider).deleteCard(card.id);
      ref.read(dataRefreshProvider.notifier).state++;
      setState(() => _selected = null);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('卡片已删除')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('删除失败: $e')),
        );
      }
    }
  }

  /// 卡片编辑/创建对话框; 返回 payload (不含 id), 取消返回 null。
  Future<Map<String, dynamic>?> _showCardEditor(KnowledgeCard? card) async {
    final titleCtrl = TextEditingController(text: card?.title ?? '');
    final contentCtrl = TextEditingController(text: card?.content ?? '');
    final aliasesCtrl = TextEditingController(
      text: card?.aliases.join('，') ?? '',
    );
    var category = card?.category ?? '通用';

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setDialogState) => AlertDialog(
            title: Text(card == null ? '新建卡片' : '编辑卡片'),
            content: SizedBox(
              width: 480,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TextField(
                      controller: titleCtrl,
                      decoration: const InputDecoration(labelText: '标题'),
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      initialValue: _categories.contains(category)
                          ? category
                          : '通用',
                      decoration: const InputDecoration(labelText: '分类'),
                      items: [
                        if (!_categories.contains('通用'))
                          const DropdownMenuItem(value: '通用', child: Text('通用')),
                        for (final c in _categories)
                          DropdownMenuItem(value: c, child: Text(c)),
                      ],
                      onChanged: (v) => setDialogState(() {
                        category = v ?? '通用';
                      }),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: aliasesCtrl,
                      decoration:
                          const InputDecoration(labelText: '别名（顿号分隔）'),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: contentCtrl,
                      maxLines: 10,
                      decoration: const InputDecoration(
                        labelText: '内容（支持 Markdown 排版）',
                        alignLabelWithHint: true,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () {
                  if (titleCtrl.text.trim().isEmpty) return;
                  Navigator.pop(ctx, {
                    'title': titleCtrl.text.trim(),
                    'content': contentCtrl.text,
                    'aliases': aliasesCtrl.text
                        .split(RegExp(r'[,，、]'))
                        .map((s) => s.trim())
                        .where((s) => s.isNotEmpty)
                        .toList(),
                    'category': category,
                  });
                },
                child: const Text('保存'),
              ),
            ],
          ),
        );
      },
    );
    return result;
  }

  @override
  Widget build(BuildContext context) {
    // 监听数据刷新信号(导入完成等),自动重新加载
    ref.listen<int>(dataRefreshProvider, (_, __) => _load());
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
        // 宽屏: 列表 | 详情 | Agent 对话侧边栏 三栏同屏
        final detail = Expanded(
          child: _selected == null
              ? const Center(child: Text('选择一张卡片'))
              : _buildDetail(_selected!),
        );
        if (constraints.maxWidth < 1100) {
          return Row(
            children: [
              SizedBox(width: 260, child: cardList),
              const VerticalDivider(width: 1),
              detail,
            ],
          );
        }
        return Row(
          children: [
            SizedBox(width: 300, child: cardList),
            const VerticalDivider(width: 1),
            detail,
            const VerticalDivider(width: 1),
            SizedBox(
              width: 360,
              child: ChatPanel(
                showModeToggle: true,
                cardTitles: _cardTitles,
                onCardTap: _onCardLinked,
              ),
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
          child: Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String?>(
                  initialValue: _category,
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
              IconButton(
                tooltip: '新建卡片',
                onPressed: _createCard,
                icon: const Icon(Icons.add),
              ),
            ],
          ),
        ),
        Expanded(
          child: filtered.isEmpty
              ? const Center(child: Text('暂无卡片'))
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  itemCount: filtered.length,
                  itemBuilder: (context, index) {
                    final card = filtered[index];
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      // 列表项: 直接用 ListTile.onTap 处理点击(避免双层手势竞争)
                      child: GlassTheme.glassTile(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                        radius: const BorderRadius.all(Radius.circular(14)),
                        child: ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                            card.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          subtitle: Text(
                            card.sourceFile.isNotEmpty
                                ? '${card.category} · ${card.sourceFile}'
                                : card.category,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          selected: _selected?.id == card.id,
                          onTap: () => _open(card),
                        ),
                      ),
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
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (onBack != null)
            TextButton.icon(
              onPressed: onBack,
              icon: const Icon(Icons.arrow_back),
              label: const Text('返回'),
            ),
          GlassTheme.glassTile(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  card.title,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ),
              Chip(label: Text(card.category)),
              IconButton(
                tooltip: '编辑',
                onPressed: () => _editCard(card),
                icon: const Icon(Icons.edit_outlined),
              ),
              IconButton(
                tooltip: '删除',
                onPressed: () => _deleteCard(card),
                icon: const Icon(Icons.delete_outline),
              ),
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
          if (card.content.isEmpty)
            const Text('（暂无内容）')
          else
            MarkdownText(
              card.content,
              cardTitles: _cardTitles,
              onCardTap: _onCardLinked,
            ),
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
          ),
        ],
      ),
    );
  }
}
