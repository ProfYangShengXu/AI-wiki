import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 运行时服务器地址配置 — 支持真机/局域网连接电脑后端。
///
/// 优先级(见 ApiConfig.baseUrl):
/// 1. `--dart-define=API_BASE_URL`(编译期注入)
/// 2. 这里持久化的地址(配对/手动配置后保存)
/// 3. 平台默认(Android 模拟器 10.0.2.2 / 其他 127.0.0.1)
class ServerConfig {
  ServerConfig._();

  static const _key = 'server_base_url';

  static String? _baseUrl;

  /// 当前已保存的服务器地址(内存缓存, 同步读取)。
  static String? get baseUrl => _baseUrl;

  /// 启动时从 SharedPreferences 加载(需在 runApp 前 await)。
  static Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final v = prefs.getString(_key);
      if (v != null && v.isNotEmpty) {
        _baseUrl = v;
      }
    } catch (e) {
      debugPrint('ServerConfig.load 失败: $e');
    }
  }

  /// 保存并更新内存值(配对/手动配置成功后调用)。
  static Future<void> save(String url) async {
    final clean = url.trim();
    _baseUrl = clean;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_key, clean);
    } catch (e) {
      debugPrint('ServerConfig.save 失败: $e');
    }
  }
}
