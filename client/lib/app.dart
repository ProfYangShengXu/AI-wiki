import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'pages/bootstrap_page.dart';
import 'pages/home_shell.dart';
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
      return const BootstrapPage();
    }
    return const HomeShell();
  }
}
