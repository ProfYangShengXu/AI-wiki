import 'package:flutter/material.dart';

import '../theme/glass_theme.dart';
import 'chat_page.dart';
import 'quiz_page.dart';
import 'settings_page.dart';
import 'upload_page.dart';
import 'wiki_page.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  /// 切回知识库 tab 时递增, WikiPage 据此强制刷新(导入完成等)。
  final _wikiReload = ValueNotifier<int>(0);

  static const _titles = ['知识库', '对话', '导入', 'Quiz', '设置'];
  late final List<Widget> _pages = [
    WikiPage(reloadNotifier: _wikiReload),
    const ChatPage(),
    const UploadPage(),
    const QuizPage(),
    const SettingsPage(),
  ];

  @override
  void dispose() {
    _wikiReload.dispose();
    super.dispose();
  }

  void _onTabSelected(int value) {
    setState(() => _index = value);
    if (value == 0) {
      _wikiReload.value++;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(title: Text(_titles[_index])),
      body: GlassTheme.background(
        context,
        child: LayoutBuilder(
          builder: (context, constraints) {
          final useRail = constraints.maxWidth >= 760;
          if (useRail) {
            return Row(
              children: [
                NavigationRail(
                  selectedIndex: _index,
                  onDestinationSelected: _onTabSelected,
                  labelType: NavigationRailLabelType.all,
                  destinations: const [
                    NavigationRailDestination(
                      icon: Icon(Icons.menu_book_outlined),
                      selectedIcon: Icon(Icons.menu_book),
                      label: Text('知识库'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.chat_bubble_outline),
                      selectedIcon: Icon(Icons.chat_bubble),
                      label: Text('对话'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.upload_outlined),
                      selectedIcon: Icon(Icons.upload),
                      label: Text('导入'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.quiz_outlined),
                      selectedIcon: Icon(Icons.quiz),
                      label: Text('Quiz'),
                    ),
                    NavigationRailDestination(
                      icon: Icon(Icons.settings_outlined),
                      selectedIcon: Icon(Icons.settings),
                      label: Text('设置'),
                    ),
                  ],
                ),
                const VerticalDivider(width: 1),
                Expanded(
                  child: GlassPageTransition(
                    key: ValueKey('page-$_index'),
                    child: IndexedStack(index: _index, children: _pages),
                  ),
                ),
              ],
            );
          }
          return GlassPageTransition(
            key: ValueKey('page-$_index'),
            child: IndexedStack(index: _index, children: _pages),
          );
          },
        ),
      ),
      bottomNavigationBar: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth >= 760) return const SizedBox.shrink();
          return NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: _onTabSelected,
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.menu_book_outlined),
                label: '知识库',
              ),
              NavigationDestination(
                icon: Icon(Icons.chat_bubble_outline),
                label: '对话',
              ),
              NavigationDestination(
                icon: Icon(Icons.upload_outlined),
                label: '导入',
              ),
              NavigationDestination(
                icon: Icon(Icons.quiz_outlined),
                label: 'Quiz',
              ),
              NavigationDestination(
                icon: Icon(Icons.settings_outlined),
                label: '设置',
              ),
            ],
          );
        },
      ),
    );
  }
}
