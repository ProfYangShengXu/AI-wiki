import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'services/sidecar_service.dart';
import 'services/tray_service.dart';

/// 客户端启动日志(安装版写 %LOCALAPPDATA%\StudyWiki-Agent\logs\client.log)。
void _log(String line) {
  try {
    final base =
        Platform.environment['LOCALAPPDATA'] ?? Directory.systemTemp.path;
    final file = File(
      '$base${Platform.pathSeparator}StudyWiki-Agent'
      '${Platform.pathSeparator}logs${Platform.pathSeparator}client.log',
    );
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(
      '${DateTime.now().toIso8601String()} $line\n',
      mode: FileMode.append,
      flush: true,
    );
  } catch (_) {}
}

Future<void> main() async {
  runZonedGuarded(() async {
    _log('客户端启动 pid=$pid');
    try {
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
      _log('UI 已启动');
    } catch (e, st) {
      _log('启动异常: $e\n$st');
    }
  }, (error, stack) {
    _log('未捕获异常: $error\n$stack');
  });
}
