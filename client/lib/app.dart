import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'pages/bootstrap_page.dart';
import 'pages/home_shell.dart';
import 'pages/pairing_page.dart';
import 'state/bootstrap_controller.dart';
import 'theme/glass_theme.dart';

class StudyWikiApp extends StatelessWidget {
  const StudyWikiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'StudyWiki-Agent',
      debugShowCheckedModeBanner: false,
      theme: GlassTheme.buildTheme(brightness: Brightness.light),
      darkTheme: GlassTheme.buildTheme(brightness: Brightness.dark),
      themeMode: ThemeMode.system,
      home: const BootstrapGate(),
    );
  }
}

/// 先检查 bootstrap 状态，再决定进入灰屏还是主界面。
class BootstrapGate extends ConsumerStatefulWidget {
  const BootstrapGate({super.key});

  @override
  ConsumerState<BootstrapGate> createState() => _BootstrapGateState();
}

class _BootstrapGateState extends ConsumerState<BootstrapGate> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(bootstrapControllerProvider.notifier).load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(bootstrapControllerProvider);
    if (state.isLoading) {
      // 转圈 + 进度文案,避免"光转圈没反应"的观感
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(),
              if (state.message.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  state.message,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ],
          ),
        ),
      );
    }
    if (state.required) {
      // 后端连不上(真机/未配对等) → 提供「设备配对」入口, 不再干等。
      if (state.isError) {
        return _ServerUnreachableView(message: state.message);
      }
      return const BootstrapPage();
    }
    return const HomeShell();
  }
}

/// 后端不可达时的引导屏: 重试 + 设备配对/配置服务器地址。
class _ServerUnreachableView extends ConsumerWidget {
  const _ServerUnreachableView({required this.message});

  final String message;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.wifi_off_rounded,
                    size: 56, color: theme.colorScheme.error),
                const SizedBox(height: 16),
                Text(
                  '无法连接本地服务',
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: 8),
                Text(
                  '手机端请先与电脑配对(扫码或输入配对码);电脑端请确认后端已启动。',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall,
                ),
                const SizedBox(height: 20),
                FilledButton.icon(
                  onPressed: () {
                    ref.read(bootstrapControllerProvider.notifier).load();
                  },
                  icon: const Icon(Icons.refresh),
                  label: const Text('重试连接'),
                ),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => const PairingPage(),
                      ),
                    );
                  },
                  icon: const Icon(Icons.qr_code_scanner),
                  label: const Text('设备配对 / 配置服务器'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
