import 'dart:io';

/// 客户端诊断日志(安装版写 %LOCALAPPDATA%\StudyWiki-Agent\logs\client.log)。
class AppLogger {
  AppLogger._();

  static void log(String line) {
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
}
