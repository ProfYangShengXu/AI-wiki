import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'services/app_logger.dart';
import 'services/sidecar_service.dart';
import 'services/tray_service.dart';
import 'services/win32_window.dart';

Future<void> main() async {
  runZonedGuarded(() async {
    AppLogger.log('客户端启动 pid=$pid');
    try {
      WidgetsFlutterBinding.ensureInitialized();

      // 先启动 UI(绝不阻塞);首帧后异步初始化 sidecar 与托盘,
      // 窗口可见性由纯 Win32 API 兜底(不依赖可能挂死的窗口插件)。
      runApp(const ProviderScope(child: StudyWikiApp()));

      if (Platform.isWindows) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          AppLogger.log('首帧完成,窗口可见性=${Win32Window.isVisible()}');
          // 兜底:1.5 秒后强制显示 + 置前 + 移回屏幕可见区域
          Future<void>.delayed(const Duration(milliseconds: 1500), () {
            final ok = Win32Window.ensureVisible();
            AppLogger.log('ensureVisible(Win32) → $ok');
            if (!ok) {
              // 标题未找到时稍后重试
              Future<void>.delayed(const Duration(seconds: 2), () {
                final retry = Win32Window.ensureVisible();
                AppLogger.log('ensureVisible 重试 → $retry');
              });
            }
          });
          unawaited(SidecarService.instance.ensureBackendRunning());
          unawaited(
            TrayService.instance
                .init()
                .timeout(const Duration(seconds: 20), onTimeout: () {}),
          );
        });
      }
      AppLogger.log('UI 已启动');
    } catch (e, st) {
      AppLogger.log('启动异常: $e\n$st');
    }
  }, (error, stack) {
    AppLogger.log('未捕获异常: $error\n$stack');
  });
}
