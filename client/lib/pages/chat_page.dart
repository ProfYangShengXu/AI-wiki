import 'package:flutter/material.dart';

import '../widgets/chat_panel.dart';

/// 对话页 — 完整页面形态的 [ChatPanel]。
class ChatPage extends StatelessWidget {
  const ChatPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const ChatPanel(showModeToggle: true);
  }
}
