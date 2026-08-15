import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'pages/bootstrap_page.dart';
import 'pages/home_shell.dart';
import 'state/bootstrap_controller.dart';

class StudyWikiApp extends StatelessWidget {
  const StudyWikiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'StudyWiki-Agent',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: const Color(0xFF2563EB),
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: const Color(0xFF2563EB),
        brightness: Brightness.dark,
      ),
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
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (state.required) {
      return const BootstrapPage();
    }
    return const HomeShell();
  }
}
