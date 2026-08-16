import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../services/offline_pack_service.dart';
import '../services/sidecar_service.dart';
import '../state/bootstrap_controller.dart';
import 'offline_pack_page.dart';
import 'pairing_page.dart';

class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final api = ref.watch(apiClientProvider);
    final bootstrap = ref.watch(bootstrapControllerProvider);

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
                  const SnackBar(content: Text('已请求停止后端(仅对本客户端拉起的进程生效)')),
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
