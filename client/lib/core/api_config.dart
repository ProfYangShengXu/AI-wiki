import 'dart:io';

import '../services/server_config.dart';

/// 后端地址解析。
///
/// 优先级：
/// 1. --dart-define=API_BASE_URL=http://x.x.x.x:8000
/// 2. Android 模拟器使用 10.0.2.2
/// 3. Windows 使用 127.0.0.1
class ApiConfig {
  ApiConfig._();

  static const _defined = String.fromEnvironment('API_BASE_URL');
  static const apiToken = String.fromEnvironment('API_TOKEN');

  static String get baseUrl {
    if (_defined.isNotEmpty) {
      return _withoutTrailingSlash(_defined);
    }
    final saved = ServerConfig.baseUrl;
    if (saved != null && saved.isNotEmpty) {
      return _withoutTrailingSlash(saved);
    }
    if (Platform.isAndroid) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://127.0.0.1:8000';
  }

  static String wsBaseUrl(String path) {
    final uri = Uri.parse(baseUrl);
    final wsHost = uri.hasPort ? '${uri.host}:${uri.port}' : uri.host;
    return 'ws://$wsHost$path';
  }

  static String _withoutTrailingSlash(String value) {
    return value.endsWith('/') ? value.substring(0, value.length - 1) : value;
  }
}
