import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';

import 'app_logger.dart';
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
    AppLogger.log('TrayService.init 开始');

    try {
      await windowManager.ensureInitialized();
      AppLogger.log('windowManager.ensureInitialized OK');
    } catch (e) {
      AppLogger.log('windowManager.ensureInitialized 失败: $e');
      return;
    }

    // 逐步骤守卫:任何一步失败都不影响窗口显示
    try {
      await windowManager.setPreventClose(true);
    } catch (e) {
      AppLogger.log('setPreventClose 失败: $e');
    }
    try {
      await windowManager.setSkipTaskbar(false);
    } catch (e) {
      AppLogger.log('setSkipTaskbar 失败: $e');
    }
    try {
      windowManager.addListener(_WindowListener());
    } catch (e) {
      AppLogger.log('addListener 失败: $e');
    }
    try {
      trayManager.addListener(TrayClickListener());
    } catch (e) {
      AppLogger.log('tray addListener 失败: $e');
    }

    try {
      final iconPath = await _extractTrayIcon();
      await trayManager.setIcon(iconPath);
      AppLogger.log('trayManager.setIcon OK');
    } catch (e) {
      AppLogger.log('trayManager.setIcon 失败: $e');
      return; // 托盘创建失败也不影响主窗口
    }
    try {
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
      AppLogger.log('托盘菜单设置 OK');
    } catch (e) {
      AppLogger.log('托盘菜单失败: $e');
    }
  }

  /// 强制显示主窗口(启动兜底:某些环境下窗口可能被隐藏/跑到屏幕外)。
  Future<void> showWindow() async {
    if (!isWindows) return;
    try {
      await windowManager.show();
      await windowManager.focus();
      AppLogger.log('showWindow 已调用');
    } catch (e) {
      AppLogger.log('showWindow 失败: $e');
    }
  }

  Future<void> hideWindow() async {
    if (!isWindows) return;
    try {
      await windowManager.hide();
      AppLogger.log('窗口已隐藏到托盘');
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
    AppLogger.log('收到窗口关闭事件 → 隐藏到托盘');
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
