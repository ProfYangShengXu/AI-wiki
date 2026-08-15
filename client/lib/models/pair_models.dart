import 'dart:convert';
import 'dart:math';

/// 配对码与配对二维码载荷相关的纯 Dart 逻辑。
///
/// 协议约定（与后端契约 §7 配对页对齐，后端端点 `POST /api/pair/verify`
/// 目前为待补项）：
/// - 配对码：6 位数字，输入时允许空格/连字符分隔，校验时归一化。
/// - 二维码载荷：`studywiki-pair` JSON 字符串，包含 code/server/device_id。
/// - 设备标识：首次生成后应持久化，用于后端去重/绑定。
///
/// 6 位配对码的校验与归一化（纯函数，便于单测）。
class PairCode {
  PairCode._();

  static final RegExp _digitOnly = RegExp(r'^[0-9]{6}$');

  /// 归一化：移除空格与连字符，便于用户按 `123 456` / `123-456` 输入。
  static String normalize(String raw) {
    return raw.replaceAll(RegExp(r'[\s-]'), '');
  }

  /// 是否为合法的 6 位纯数字配对码。
  static bool isValid(String raw) {
    return _digitOnly.hasMatch(normalize(raw));
  }

  /// 生成一个 6 位随机配对码（带前导零）。
  static String generate({Random? random}) {
    final rng = random ?? Random();
    return (rng.nextInt(1000000)).toString().padLeft(6, '0');
  }
}

/// 生成稳定、可持久化的设备标识（16 位十六进制）。
///
/// 使用 [Random.secure] 在可用时取加密安全随机源；不可用时回退到
/// 基于时间戳的伪随机。调用方应将其持久化（如 shared_preferences）。
String generateDeviceId({Random? random}) {
  final rng = random ?? _secureRandom();
  const hex = '0123456789abcdef';
  final buffer = StringBuffer();
  for (var i = 0; i < 16; i++) {
    buffer.write(hex[rng.nextInt(16)]);
  }
  return buffer.toString();
}

Random _secureRandom() {
  try {
    return Random.secure();
  } catch (_) {
    return Random(DateTime.now().microsecondsSinceEpoch);
  }
}

/// 配对二维码载荷。
///
/// 二维码内容为单行 JSON，例如：
/// ```json
/// {"v":1,"type":"studywiki-pair","code":"123456",
///  "server":"http://192.168.1.10:8000","device_id":"1a2b3c4d5e6f7081"}
/// ```
class PairPayload {
  const PairPayload({
    required this.code,
    required this.server,
    required this.deviceId,
  });

  static const int currentVersion = 1;
  static const String type = 'studywiki-pair';

  final String code;
  final String server;
  final String deviceId;

  /// 序列化为二维码内容（单行 JSON）。
  String encode() {
    return jsonEncode({
      'v': currentVersion,
      'type': type,
      'code': code,
      'server': server,
      'device_id': deviceId,
    });
  }

  /// 从二维码内容解析；非本协议内容或非法时返回 null。
  static PairPayload? decode(String raw) {
    try {
      final map = jsonDecode(raw);
      if (map is! Map<String, dynamic>) return null;
      if (map['type'] != type) return null;
      final code = map['code'];
      final server = map['server'];
      final deviceId = map['device_id'];
      if (code is! String || server is! String || deviceId is! String) {
        return null;
      }
      return PairPayload(code: code, server: server, deviceId: deviceId);
    } catch (_) {
      return null;
    }
  }
}

/// `POST /api/pair/verify` 的客户端结果封装。
class PairResult {
  const PairResult({
    required this.ok,
    required this.message,
    this.errorCode,
    this.notImplemented = false,
  });

  final bool ok;

  /// 面向用户的提示信息（含 code 时已格式化）。
  final String message;
  final String? errorCode;

  /// 后端未启用配对（404/501）时为 true。
  final bool notImplemented;
}
