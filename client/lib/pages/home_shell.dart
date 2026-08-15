import 'package:flutter/material.dart';

import 'chat_page.dart';
import 'quiz_page.dart';
import 'settings_page.dart';
import 'wiki_page.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _titles = ['知识库', '对话', 'Quiz', '设置'];
  static const _pages = [
    WikiPage(),
    ChatPage(),
    QuizPage(),
    SettingsPage(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_titles[_index])),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final useRail = constraints.maxWidth >= 760;
          if (useRail) {
            return Row(
              children: [
                NavigationRail(
                  selectedIndex: _index,
                  onDestinationSelected: (value) =>
                      setState(() => _index = value),
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
                Expanded(child: IndexedStack(index: _index, children: _pages)),
              ],
            );
          }
          return IndexedStack(index: _index, children: _pages);
        },
      ),
      bottomNavigationBar: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth >= 760) return const SizedBox.shrink();
          return NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (value) => setState(() => _index = value),
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
