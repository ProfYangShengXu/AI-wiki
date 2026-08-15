import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';

import 'sidecar_service.dart';

/// Windows 系统托盘(微信/QQ 形态):
/// - 点击关闭按钮 → 最小化到托盘;
/// - 托盘菜单:显示主窗口 / 退出(退出时带停 sidecar)。
///
/// 非 Windows 平台为 no-op,保证 Linux CI 测试不受影响。
class TrayService {
  TrayService._();

  static final TrayService instance = TrayService._();

  bool _initialized = false;

  bool get isWindows => Platform.isWindows;

  Future<void> init() async {
    if (!isWindows || _initialized) return;
    _initialized = true;
    try {
      await windowManager.ensureInitialized();
      await windowManager.setPreventClose(true);
      windowManager.setSkipTaskbar(false);
      windowManager.addListener(_WindowListener());
      trayManager.addListener(TrayClickListener());

      final iconPath = await _extractTrayIcon();
      await trayManager.setIcon(iconPath);
      await trayManager.setToolTip('StudyWiki-Agent');
      await trayManager.setContextMenu(
        Menu(
          items: [
            MenuItem(key: 'show', label: '显示主窗口'),
            MenuItem.separator(),
            MenuItem(key: 'quit', label: '退出'),
          ],
        ),
      );
    } catch (e) {
      // 托盘初始化失败不影响主流程
      debugPrint('TrayService init failed: $e');
    }
  }

  /// 从 assets 提取托盘图标到临时目录,返回绝对路径。
  Future<String> _extractTrayIcon() async {
    final data = await rootBundle.load('assets/tray_icon.ico');
    final file = File(
      '${Directory.systemTemp.path}${Platform.pathSeparator}studywiki_tray_icon.ico',
    );
    await file.writeAsBytes(data.buffer.asUint8List(), flush: true);
    return file.path;
  }

  Future<void> showWindow() async {
    if (!isWindows) return;
    try {
      await windowManager.show();
      await windowManager.focus();
    } catch (_) {}
  }

  Future<void> hideWindow() async {
    if (!isWindows) return;
    try {
      await windowManager.hide();
    } catch (_) {}
  }

  Future<void> dispose() async {
    if (!isWindows || !_initialized) return;
    try {
      await trayManager.destroy();
    } catch (_) {}
    try {
      await windowManager.destroy();
    } catch (_) {}
  }
}

class _WindowListener extends WindowListener {
  @override
  void onWindowClose() {
    unawaited(TrayService.instance.hideWindow());
  }
}

/// 托盘菜单点击处理:挂到 trayManager 的全局监听。
class TrayClickListener with TrayListener {
  @override
  void onTrayIconMouseDown() {
    unawaited(TrayService.instance.showWindow());
  }

  @override
  void onTrayIconRightMouseDown() {
    unawaited(trayManager.popUpContextMenu());
  }

  @override
  void onTrayMenuItemClick(MenuItem menuItem) {
    switch (menuItem.key) {
      case 'show':
        unawaited(TrayService.instance.showWindow());
        break;
      case 'quit':
        unawaited(_quit());
        break;
      default:
        break;
    }
  }

  Future<void> _quit() async {
    await SidecarService.instance.stopSidecar();
    await TrayService.instance.dispose();
    exit(0);
  }
}
