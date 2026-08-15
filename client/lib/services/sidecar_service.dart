import 'dart:async';
import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

/// Windows sidecar 管理:自动拉起/健康检查/退出带停后端 exe。
///
/// 定位顺序:
/// 1. 用户在设置里指定的路径(shared_preferences: `sidecar_path`);
/// 2. 客户端同目录的 `sidecar/study-wiki-core.exe`;
/// 3. 客户端同目录的 `study-wiki-core.exe`。
///
/// 非 Windows 平台:所有方法为安全 no-op(Android 连远程服务)。
class SidecarService {
  SidecarService._();

  static final SidecarService instance = SidecarService._();

  static const _prefSidecarPath = 'sidecar_path';
  static const _healthTimeout = Duration(seconds: 2);
  static const _startTimeout = Duration(seconds: 40);

  Process? _process;
  int? _pid;
  bool _startedByUs = false;
  String? _customPath;

  bool get isWindows => Platform.isWindows;

  /// 读取用户自定义 sidecar 路径(设置页写入)。
  Future<String?> loadCustomPath() async {
    if (!isWindows) return null;
    try {
      final prefs = await SharedPreferences.getInstance();
      _customPath = prefs.getString(_prefSidecarPath);
    } catch (_) {}
    return _customPath;
  }

  Future<void> saveCustomPath(String? path) async {
    if (!isWindows) return;
    _customPath = (path == null || path.trim().isEmpty) ? null : path.trim();
    try {
      final prefs = await SharedPreferences.getInstance();
      if (_customPath == null) {
        await prefs.remove(_prefSidecarPath);
      } else {
        await prefs.setString(_prefSidecarPath, _customPath!);
      }
    } catch (_) {}
  }

  /// 候选 exe 路径(按优先级)。
  Future<List<String>> candidatePaths() async {
    await loadCustomPath();
    final candidates = <String>[];
    final execDir = File(Platform.resolvedExecutable).parent.path;
    if (_customPath != null) candidates.add(_customPath!);
    candidates.add('$execDir${Platform.pathSeparator}sidecar${Platform.pathSeparator}study-wiki-core.exe');
    candidates.add('$execDir${Platform.pathSeparator}study-wiki-core.exe');
    candidates.add('study-wiki-core.exe'); // CWD 兜底
    return candidates;
  }

  Future<String?> resolveSidecarExe() async {
    for (final path in await candidatePaths()) {
      try {
        if (await File(path).exists()) return path;
      } catch (_) {}
    }
    return null;
  }

  /// 后端是否已就绪(/health 返回 200)。
  Future<bool> isBackendRunning() async {
    final client = HttpClient()..connectionTimeout = _healthTimeout;
    try {
      final req = await client
          .getUrl(Uri.parse('http://127.0.0.1:8000/health'))
          .timeout(_healthTimeout);
      final resp = await req.close().timeout(_healthTimeout);
      await resp.drain<void>();
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    } finally {
      client.close(force: true);
    }
  }

  /// 确保后端运行:已在跑则直接返回,否则定位 exe 拉起并轮询健康检查。
  ///
  /// 返回 [SidecarStartResult],任何失败都不会抛异常。
  Future<SidecarStartResult> ensureBackendRunning() async {
    if (!isWindows) {
      return SidecarStartResult(true, false, '非 Windows 平台,跳过 sidecar');
    }
    if (await isBackendRunning()) {
      return SidecarStartResult(true, false, '后端已在运行');
    }
    final exe = await resolveSidecarExe();
    if (exe == null) {
      return SidecarStartResult(false, false, '未找到 study-wiki-core.exe,请手动启动后端或在设置中指定路径');
    }
    try {
      final exeFile = File(exe);
      final workingDir = exeFile.parent.path;
      _process = await Process.start(
        exe,
        const [],
        workingDirectory: workingDir,
        mode: ProcessStartMode.normal,
      );
      _pid = _process!.pid;
      _startedByUs = true;
      // 排空输出流,避免后端日志填满管道缓冲区
      unawaited(_process!.stdout.drain<void>());
      unawaited(_process!.stderr.drain<void>());
      unawaited(
        _process!.exitCode.then((_) {
          _process = null;
          _pid = null;
          _startedByUs = false;
        }),
      );
    } catch (e) {
      return SidecarStartResult(false, false, '拉起后端失败: $e');
    }

    final deadline = DateTime.now().add(_startTimeout);
    while (DateTime.now().isBefore(deadline)) {
      if (await isBackendRunning()) {
        return SidecarStartResult(true, true, '后端已就绪($exe)');
      }
      await Future<void>.delayed(const Duration(seconds: 1));
    }
    return SidecarStartResult(false, true, '后端启动超时(40s),请查看 logs/ 目录');
  }

  /// 停止由本客户端拉起的后端进程。
  Future<void> stopSidecar() async {
    if (!isWindows) return;
    final pid = _pid;
    if (pid != null) {
      try {
        Process.killPid(pid);
      } catch (_) {}
    }
    _process = null;
    _pid = null;
    _startedByUs = false;
  }

  bool get startedByUs => _startedByUs;
}

class SidecarStartResult {
  SidecarStartResult(this.ok, this.started, this.message);

  final bool ok;
  final bool started;
  final String message;
}
