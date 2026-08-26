import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../services/offline_pack_service.dart';
import '../services/sidecar_service.dart';
import '../state/bootstrap_controller.dart';
import 'offline_pack_page.dart';
import 'pairing_page.dart';

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  Map<String, dynamic>? _metrics;

  @override
  void initState() {
    super.initState();
    _loadMetrics();
  }

  Future<void> _loadMetrics() async {
    try {
      final m = await ref.read(apiClientProvider).getMetrics();
      if (mounted) setState(() => _metrics = m);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final api = ref.watch(apiClientProvider);
    final bootstrap = ref.watch(bootstrapControllerProvider);
    final tokenUsage = (_metrics?['token_usage'] as Map?) ?? const {};
    final promptTokens = tokenUsage['prompt'] ?? 0;
    final completionTokens = tokenUsage['completion'] ?? 0;
    final totalTokens = tokenUsage['total'] ?? 0;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        ListTile(
          leading: const Icon(Icons.dns_outlined),
          title: const Text('服务地址'),
          subtitle: Text(api.baseUrl),
        ),
        ListTile(
          leading: const Icon(Icons.vpn_key_outlined),
          title: const Text('当前 Key'),
          subtitle: Text(
            bootstrap.keyTail.isEmpty ? '未配置' : bootstrap.keyTail,
          ),
        ),
        ListTile(
          leading: const Icon(Icons.hub_outlined),
          title: const Text('供应商'),
          subtitle: Text(bootstrap.provider),
        ),
        // Token 消耗统计
        ListTile(
          leading: const Icon(Icons.data_usage_outlined),
          title: const Text('Token 消耗'),
          subtitle: Text(
            '输入 ${_fmtToken(promptTokens)} · 输出 ${_fmtToken(completionTokens)} · 总计 ${_fmtToken(totalTokens)}',
          ),
          trailing: IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: '刷新',
            onPressed: _loadMetrics,
          ),
        ),
        ListTile(
          leading: const Icon(Icons.tune_outlined),
          title: const Text('切换 API 设置'),
          subtitle: const Text('更换供应商/Key/模型, 即时生效无需重启'),
          trailing: const Icon(Icons.chevron_right),
          onTap: _showApiSettings,
        ),
        if (SidecarService.instance.isWindows) ..._sidecarTiles(context),
        const Divider(),
        ListTile(
          leading: const Icon(Icons.qr_code_scanner),
          title: const Text('设备配对'),
          subtitle: const Text('输入配对码或生成配对二维码'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const PairingPage()),
            );
          },
        ),
        ListTile(
          leading: const Icon(Icons.cloud_off_outlined),
          title: const Text('离线知识库'),
          subtitle: const Text('浏览本地缓存的离线卡片'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const OfflinePackPage()),
            );
          },
        ),
        ListTile(
          leading: const Icon(Icons.download_outlined),
          title: const Text('导出离线知识包'),
          subtitle: const Text('拉取全量卡片并缓存为 JSON + Markdown'),
          onTap: () => _exportPack(context, ref),
        ),
        ListTile(
          leading: const Icon(Icons.upload_outlined),
          title: const Text('回传离线评分'),
          subtitle: const Text('将离线 Quiz 评分批量 POST /api/quiz/grade'),
          onTap: () => _flushGrades(context, ref),
        ),
        const Divider(),
        FilledButton.icon(
          onPressed: () =>
              ref.read(bootstrapControllerProvider.notifier).load(),
          icon: const Icon(Icons.refresh),
          label: const Text('重新检查配置'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('如需更换 Key，请删除服务端 .env 后重启服务'),
              ),
            );
          },
          icon: const Icon(Icons.info_outline),
          label: const Text('如何更换 API Key'),
        ),
      ],
    );
  }

  String _fmtToken(dynamic v) {
    final n = v is int ? v : (v is num ? v.toInt() : 0);
    if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(1)}M';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}k';
    return '$n';
  }

  /// 切换 API 设置对话框: 选供应商/Key/BaseURL/模型, 保存后即时生效。
  Future<void> _showApiSettings() async {
    final bootstrap = ref.read(bootstrapControllerProvider);
    final baseUrlCtrl = TextEditingController(text: '');
    final modelCtrl = TextEditingController(text: '');
    final keyCtrl = TextEditingController(text: '');

    const providers = [
      ('deepseek', 'DeepSeek'),
      ('openai', 'OpenAI'),
      ('kimi', 'Kimi (月之暗面)'),
      ('glm', 'GLM (智谱)'),
      ('grok', 'Grok (xAI)'),
      ('anthropic', 'Claude (Anthropic)'),
      ('gemini', 'Gemini (Google)'),
    ];
    // provider → (model, baseUrl) 默认值
    const defaults = {
      'deepseek': ('deepseek-v4-flash', 'https://api.deepseek.com'),
      'openai': ('gpt-4o-mini', 'https://api.openai.com/v1'),
      'kimi': ('moonshot-v1-8k', 'https://api.moonshot.cn/v1'),
      'glm': ('glm-4-flash', 'https://open.bigmodel.cn/api/paas/v4'),
      'grok': ('grok-3-mini', 'https://api.x.ai/v1'),
      'anthropic': ('claude-sonnet-4-5', 'https://api.anthropic.com'),
      'gemini': ('gemini-2.0-flash', ''),
    };

    var provider = bootstrap.provider;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('切换 API 设置'),
          content: SizedBox(
            width: 420,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  DropdownButton<String>(
                    value: provider,
                    isExpanded: true,
                    items: [
                      for (final (id, label) in providers)
                        DropdownMenuItem(value: id, child: Text(label)),
                    ],
                    onChanged: (v) {
                      if (v == null) return;
                      setDialogState(() {
                        provider = v;
                        final d = defaults[v] ?? defaults['deepseek']!;
                        modelCtrl.text = d.$1;
                        baseUrlCtrl.text = d.$2;
                      });
                    },
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: keyCtrl,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'API Key',
                      hintText: 'sk-...',
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: baseUrlCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Base URL(可留空)',
                      hintText: 'https://api.xxx.com/v1',
                    ),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: modelCtrl,
                    decoration: const InputDecoration(labelText: '模型'),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () {
                if (keyCtrl.text.trim().isEmpty) {
                  ScaffoldMessenger.of(ctx).showSnackBar(
                    const SnackBar(content: Text('请填写 API Key')),
                  );
                  return;
                }
                Navigator.pop(ctx, true);
              },
              child: const Text('保存并切换'),
            ),
          ],
        ),
      ),
    );
    if (ok != true || !mounted) return;

    try {
      final updates = <String, String>{
        'LLM_PROVIDER': provider,
        if (baseUrlCtrl.text.trim().isNotEmpty)
          _providerBaseUrlEnv(provider): baseUrlCtrl.text.trim(),
        if (modelCtrl.text.trim().isNotEmpty)
          _providerModelEnv(provider): modelCtrl.text.trim(),
        _providerKeyEnv(provider): keyCtrl.text.trim(),
      };
      await ref.read(apiClientProvider).saveSettings(updates);
      await ref.read(bootstrapControllerProvider.notifier).load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('✓ 已切换, 即时生效')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('切换失败: $e')),
        );
      }
    }
  }

  String _providerKeyEnv(String provider) {
    switch (provider) {
      case 'openai': return 'OPENAI_API_KEY';
      case 'kimi': return 'KIMI_API_KEY';
      case 'glm': return 'GLM_API_KEY';
      case 'grok': return 'GROK_API_KEY';
      case 'anthropic': return 'ANTHROPIC_API_KEY';
      case 'gemini': return 'GEMINI_API_KEY';
      default: return 'DEEPSEEK_API_KEY';
    }
  }

  String _providerModelEnv(String provider) {
    switch (provider) {
      case 'openai': return 'OPENAI_MODEL';
      case 'kimi': return 'KIMI_MODEL';
      case 'glm': return 'GLM_MODEL';
      case 'grok': return 'GROK_MODEL';
      case 'anthropic': return 'ANTHROPIC_MODEL';
      case 'gemini': return 'GEMINI_MODEL';
      default: return 'DEEPSEEK_MODEL';
    }
  }

  String _providerBaseUrlEnv(String provider) {
    switch (provider) {
      case 'openai': return 'OPENAI_BASE_URL';
      case 'kimi': return 'KIMI_BASE_URL';
      case 'glm': return 'GLM_BASE_URL';
      case 'grok': return 'GROK_BASE_URL';
      case 'anthropic': return 'ANTHROPIC_BASE_URL';
      default: return 'DEEPSEEK_BASE_URL';
    }
  }

  /// Windows 本地服务(sidecar)管理项。
  List<Widget> _sidecarTiles(BuildContext context) {
    return [
      const Divider(),
      const ListTile(
        leading: Icon(Icons.settings_applications_outlined),
        title: Text('本地服务'),
        subtitle: Text('客户端自动拉起/停止后端 exe'),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Wrap(
          spacing: 8,
          children: [
            OutlinedButton.icon(
              icon: const Icon(Icons.play_arrow),
              label: const Text('启动后端'),
              onPressed: () async {
                final r = await SidecarService.instance.ensureBackendRunning();
                if (!context.mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(r.message)),
                );
              },
            ),
            OutlinedButton.icon(
              icon: const Icon(Icons.stop),
              label: const Text('停止后端'),
              onPressed: () async {
                await SidecarService.instance.stopSidecar();
                if (!context.mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('已停止后端服务')),
                );
              },
            ),
          ],
        ),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: FutureBuilder<String?>(
          future: SidecarService.instance.resolveSidecarExe(),
          builder: (context, snap) {
            final path = snap.data;
            return Text(
              path == null
                  ? '未找到 study-wiki-core.exe:请将其放在客户端目录,或与后端手动连用'
                  : 'sidecar: $path',
              style: TextStyle(
                fontSize: 12,
                color: path == null
                    ? Theme.of(context).colorScheme.error
                    : Theme.of(context).colorScheme.outline,
              ),
            );
          },
        ),
      ),
    ];
  }

  Future<void> _exportPack(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final pack = await ref.read(offlinePackServiceProvider).exportAndSave();
      messenger.showSnackBar(
        SnackBar(content: Text('已导出 ${pack.cardCount} 张卡片到本地缓存')),
      );
    } catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('导出失败: $e')),
      );
    }
  }

  Future<void> _flushGrades(BuildContext context, WidgetRef ref) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final result = await ref.read(offlinePackServiceProvider).flushPendingGrades();
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            '回传完成：成功 ${result.sent} 条，失败 ${result.failed} 条，剩余 ${result.remaining} 条',
          ),
        ),
      );
    } catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('回传失败: $e')),
      );
    }
  }
}
