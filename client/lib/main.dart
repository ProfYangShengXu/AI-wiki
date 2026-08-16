import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'services/app_logger.dart';
import 'services/sidecar_service.dart';
import 'services/tray_service.dart';

Future<void> main() async {
  runZonedGuarded(() async {
    AppLogger.log('客户端启动 pid=$pid');
    try {
      WidgetsFlutterBinding.ensureInitialized();

      // 先启动 UI(绝不阻塞);首帧后再异步初始化 Windows sidecar 与托盘,
      // 避免在消息循环启动前调用原生托盘接口导致白屏不响应。
      runApp(const ProviderScope(child: StudyWikiApp()));

      if (Platform.isWindows) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          // 启动兜底:窗口若被隐藏/跑到屏幕外,2 秒后强制显示并聚焦。
          Future<void>.delayed(const Duration(seconds: 2), () {
            unawaited(TrayService.instance.showWindow());
          });
          unawaited(SidecarService.instance.ensureBackendRunning());
          unawaited(
            TrayService.instance
                .init()
                .timeout(const Duration(seconds: 15), onTimeout: () {}),
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
