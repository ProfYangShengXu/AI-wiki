import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'services/sidecar_service.dart';
import 'services/tray_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 先启动 UI(绝不阻塞);首帧后再异步初始化 Windows sidecar 与托盘,
  // 避免在消息循环启动前调用原生托盘接口导致白屏不响应。
  runApp(const ProviderScope(child: StudyWikiApp()));

  if (Platform.isWindows) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(SidecarService.instance.ensureBackendRunning());
      unawaited(
        TrayService.instance
            .init()
            .timeout(const Duration(seconds: 15), onTimeout: () {}),
      );
    });
  }
}
