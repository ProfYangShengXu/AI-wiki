import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'services/app_logger.dart';
import 'services/server_config.dart';
import 'services/sidecar_service.dart';
import 'services/tray_service.dart';
import 'services/win32_window.dart';

/// 单实例锁: 独占锁文件, 若已被本机另一实例持有则直接退出,
/// 避免多个客户端窗口 + 重复轮询后端导致的进程堆积/卡顿。
RandomAccessFile? _instanceLock;

bool _acquireSingleInstanceLock() {
  try {
    final base =
        Platform.environment['LOCALAPPDATA'] ?? Directory.systemTemp.path;
    final dir = Directory(
      '$base${Platform.pathSeparator}StudyWiki-Agent',
    );
    dir.createSync(recursive: true);
    final lockFile = File(
      '${dir.path}${Platform.pathSeparator}instance.lock',
    );
    _instanceLock = lockFile.openSync(mode: FileMode.write);
    // 尝试独占: 失败说明已有实例持有
    try {
      _instanceLock!.lockSync(FileLock.exclusive, 0, 1);
      return true;
    } catch (_) {
      _instanceLock?.closeSync();
      _instanceLock = null;
      return false;
    }
  } catch (_) {
    // 锁机制失败不阻断启动(降级为允许多实例)
    return true;
  }
}

Future<void> main() async {
  runZonedGuarded(() async {
    AppLogger.log('客户端启动 pid=$pid');
    try {
      WidgetsFlutterBinding.ensureInitialized();

      // 启动前加载运行时服务器地址(真机配对/手动配置), 供 ApiConfig 使用。
      await ServerConfig.load();

      // 单实例检查: 已有实例运行则退出
      if (Platform.isWindows && !_acquireSingleInstanceLock()) {
        AppLogger.log('检测到已有实例在运行, 本实例退出');
        return;
      }

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
          unawaited(
            SidecarService.instance
                .ensureBackendRunning()
                .then((r) => AppLogger.log('sidecar: ${r.message}')),
          );
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
