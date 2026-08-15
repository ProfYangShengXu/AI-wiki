import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'services/sidecar_service.dart';
import 'services/tray_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Windows: 自动拉起本地后端 sidecar(微信/QQ 形态:双击客户端即可用),
  // 并初始化系统托盘。非 Windows 平台为 no-op。
  if (Platform.isWindows) {
    unawaited(SidecarService.instance.ensureBackendRunning());
    await TrayService.instance.init();
  }

  runApp(const ProviderScope(child: StudyWikiApp()));
}
