import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/api_client.dart';
import '../models/knowledge_card.dart';
import '../models/offline_pack.dart';

/// 离线知识包与 Quiz 回传队列服务（纯 Dart，仅依赖 ApiClient 与
/// shared_preferences，不引入重型数据库）。
///
/// 职责：
/// 1. 从 `GET /api/cards?limit=1000` 导出离线包（JSON + Markdown）。
/// 2. 将离线包以 JSON 字符串缓存到 shared_preferences。
/// 3. 离线浏览缓存卡片。
/// 4. 离线 Quiz 评分结果进入待回传队列，网络恢复后批量
///    `POST /api/quiz/grade` 冲刷。
class OfflinePackService {
  OfflinePackService({ApiClient? api}) : _api = api ?? ApiClient();

  static const String packCacheKey = 'offline_pack_json_v1';
  static const String gradeQueueKey = 'offline_quiz_grade_queue_v1';

  final ApiClient _api;

  // ── 导出 ────────────────────────────────────────────────

  /// 拉取全量卡片（limit=1000）并构建离线包。
  Future<OfflinePack> exportPack() async {
    final cards = await _api.listCards(limit: 1000);
    return OfflinePack(
      cards: cards,
      server: _api.baseUrl,
      exportedAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  /// 导出并落盘到本地缓存。
  Future<OfflinePack> exportAndSave() async {
    final pack = await exportPack();
    await savePack(pack);
    return pack;
  }

  /// 将离线包 JSON 字符串写入 shared_preferences。
  Future<void> savePack(OfflinePack pack) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(packCacheKey, jsonEncode(pack.toJson()));
  }

  /// 读取缓存离线包；不存在或已损坏时返回 null。
  Future<OfflinePack?> loadPack() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(packCacheKey);
    if (raw == null) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        return OfflinePack.fromJson(decoded);
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// 离线浏览缓存卡片（等价于读取离线包中的卡片列表）。
  Future<List<KnowledgeCard>> cachedCards() async {
    final pack = await loadPack();
    return pack?.cards ?? const [];
  }

  /// 是否存在本地离线缓存。
  Future<bool> hasCache() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.containsKey(packCacheKey);
  }

  // ── Quiz 回传队列 ───────────────────────────────────────

  /// 将一条评分请求追加到待回传队列。
  Future<void> enqueueGrade(QuizGradeRequest request) async {
    final prefs = await SharedPreferences.getInstance();
    final queue = _readQueue(prefs);
    queue.add(request.toJson());
    await _writeQueue(prefs, queue);
  }

  /// 读取当前待回传队列（按入队顺序）。
  Future<List<QuizGradeRequest>> pendingGrades() async {
    final prefs = await SharedPreferences.getInstance();
    return _readQueue(prefs)
        .map((e) => QuizGradeRequest.fromJson(e))
        .whereType<QuizGradeRequest>()
        .toList();
  }

  /// 冲刷待回传队列：逐条 `POST /api/quiz/grade`，成功者移出队列，
  /// 失败者保留（网络恢复后可再次冲刷）。
  Future<QuizFlushResult> flushPendingGrades() async {
    final prefs = await SharedPreferences.getInstance();
    final queue = _readQueue(prefs);
    var sent = 0;
    var failed = 0;
    final remaining = <Map<String, dynamic>>[];

    for (final item in queue) {
      final request = QuizGradeRequest.fromJson(item);
      if (request == null) {
        // 损坏条目直接丢弃，避免永久阻塞队列。
        continue;
      }
      try {
        await _api.gradeQuiz(cardId: request.cardId, answers: request.answers);
        sent++;
      } catch (_) {
        failed++;
        remaining.add(item);
      }
    }

    await _writeQueue(prefs, remaining);
    return QuizFlushResult(sent: sent, failed: failed, remaining: remaining.length);
  }

  /// 清空待回传队列。
  Future<void> clearPendingGrades() async {
    final prefs = await SharedPreferences.getInstance();
    await _writeQueue(prefs, const []);
  }

  List<Map<String, dynamic>> _readQueue(SharedPreferences prefs) {
    final raw = prefs.getString(gradeQueueKey);
    if (raw == null || raw.isEmpty) return [];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is List) {
        return decoded
            .whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList();
      }
      return [];
    } catch (_) {
      return [];
    }
  }

  Future<void> _writeQueue(
    SharedPreferences prefs,
    List<Map<String, dynamic>> queue,
  ) async {
    await prefs.setString(gradeQueueKey, jsonEncode(queue));
  }
}

/// 队列冲刷结果。
class QuizFlushResult {
  const QuizFlushResult({
    required this.sent,
    required this.failed,
    required this.remaining,
  });

  final int sent;
  final int failed;
  final int remaining;
}

final offlinePackServiceProvider = Provider<OfflinePackService>(
  (ref) => OfflinePackService(api: ref.watch(apiClientProvider)),
);
