import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/knowledge_card.dart';
import '../services/offline_pack_service.dart';
import '../widgets/app_snackbar.dart';

/// 离线知识库：浏览本地缓存的离线包卡片，支持重新导出。
class OfflinePackPage extends ConsumerStatefulWidget {
  const OfflinePackPage({super.key});

  @override
  ConsumerState<OfflinePackPage> createState() => _OfflinePackPageState();
}

class _OfflinePackPageState extends ConsumerState<OfflinePackPage> {
  List<KnowledgeCard> _cards = const [];
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
      final cards = await ref.read(offlinePackServiceProvider).cachedCards();
      if (!mounted) return;
      setState(() {
        _cards = cards;
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

  Future<void> _export() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final pack = await ref.read(offlinePackServiceProvider).exportAndSave();
      if (!mounted) return;
      setState(() {
        _cards = pack.cards;
        _loading = false;
      });
      AppSnack.info(context, '已导出并缓存 ${pack.cardCount} 张卡片');
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
      AppSnack.error(context, '导出失败: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('离线知识库'),
        actions: [
          IconButton(
            onPressed: _loading ? null : _export,
            icon: const Icon(Icons.download),
            tooltip: '重新导出',
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('离线包加载失败: $_error', textAlign: TextAlign.center),
            const SizedBox(height: 8),
            FilledButton(onPressed: _load, child: const Text('重试')),
          ],
        ),
      );
    }
    if (_cards.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('暂无离线缓存'),
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: _export,
              icon: const Icon(Icons.download),
              label: const Text('立即导出离线包'),
            ),
          ],
        ),
      );
    }
    return ListView.builder(
      itemCount: _cards.length,
      itemBuilder: (context, index) {
        final card = _cards[index];
        return ListTile(
          title: Text(card.title),
          subtitle: Text(card.category),
          onTap: () => _showDetail(card),
        );
      },
    );
  }

  void _showDetail(KnowledgeCard card) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(card.title),
        content: SingleChildScrollView(
          child: Text(card.content.isEmpty ? '（暂无内容）' : card.content),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  }
}
