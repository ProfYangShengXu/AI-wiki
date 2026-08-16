import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:tray_manager/tray_manager.dart';

import 'app_logger.dart';
import 'sidecar_service.dart';
import 'win32_window.dart';

/// Windows 系统托盘(微信/QQ 形态)。
///
/// 窗口控制走纯 Win32 API(win32_window.dart),不再依赖 window_manager
/// (其原生调用在部分机器上挂死,导致窗口不可见)。
/// 当前行为:点击托盘图标 → 显示主窗口;菜单 → 显示 / 退出(退出带停后端)。
/// 关闭窗口 = 退出程序(后端保留运行,下次启动自动复用)。
class TrayService {
  TrayService._();

  static final TrayService instance = TrayService._();

  bool _initialized = false;

  bool get isWindows => Platform.isWindows;

  Future<void> init() async {
    if (!isWindows || _initialized) return;
    _initialized = true;
    AppLogger.log('TrayService.init 开始(Win32 方案)');
    try {
      trayManager.addListener(TrayClickListener());
    } catch (e) {
      AppLogger.log('tray addListener 失败: $e');
    }
    try {
      final iconPath = await _extractTrayIcon();
      await trayManager
          .setIcon(iconPath)
          .timeout(const Duration(seconds: 10));
      AppLogger.log('trayManager.setIcon OK');
    } catch (e) {
      AppLogger.log('trayManager.setIcon 失败: $e');
      return; // 托盘失败不影响主窗口
    }
    try {
      await trayManager
          .setToolTip('StudyWiki-Agent')
          .timeout(const Duration(seconds: 5));
      await trayManager
          .setContextMenu(
            Menu(
              items: [
                MenuItem(key: 'show', label: '显示主窗口'),
                MenuItem.separator(),
                MenuItem(key: 'quit', label: '退出'),
              ],
            ),
          )
          .timeout(const Duration(seconds: 5));
      AppLogger.log('托盘菜单设置 OK');
    } catch (e) {
      AppLogger.log('托盘菜单失败: $e');
    }
  }

  Future<void> showWindow() async {
    if (!isWindows) return;
    final ok = Win32Window.show();
    AppLogger.log('showWindow(Win32) → $ok');
    if (!ok) {
      // 窗口还没创建(首次启动首帧前):稍后重试一次
      await Future<void>.delayed(const Duration(seconds: 2));
      final retry = Win32Window.show();
      AppLogger.log('showWindow 重试 → $retry');
    }
  }

  Future<void> dispose() async {
    if (!isWindows || !_initialized) return;
    try {
      await trayManager.destroy();
    } catch (_) {}
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
}

/// 托盘菜单点击处理。
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
