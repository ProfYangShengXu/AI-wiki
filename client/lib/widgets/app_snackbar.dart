import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// 统一的 SnackBar: 提示类白底黑字, 报错类红底黑字, 均带「复制」操作。
class AppSnack {
  AppSnack._();

  /// 提示/成功类 — 白底黑字。
  static void info(BuildContext context, String msg) {
    _show(context, msg, error: false);
  }

  /// 报错类 — 红底黑字。
  static void error(BuildContext context, String msg) {
    _show(context, msg, error: true);
  }

  static void _show(BuildContext context, String msg, {required bool error}) {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(
      SnackBar(
        backgroundColor: error ? const Color(0xFFF87171) : Colors.white,
        content: Text(
          msg,
          style: const TextStyle(color: Colors.black),
        ),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        action: SnackBarAction(
          label: '复制',
          textColor: Colors.black,
          onPressed: () {
            Clipboard.setData(ClipboardData(text: msg));
          },
        ),
      ),
    );
  }
}

/// 复制文本到剪贴板(不弹窗)。
Future<void> copyToClipboard(String text) {
  return Clipboard.setData(ClipboardData(text: text));
}
