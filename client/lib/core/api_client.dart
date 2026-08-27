import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/bootstrap_models.dart';
import '../models/knowledge_card.dart';
import '../models/pair_models.dart';
import '../models/quiz_card.dart';
import '../services/server_config.dart';
import 'api_config.dart';
import 'error_codes.dart';

/// 统一业务异常：携带后端错误码与 HTTP 状态码。
///
/// 页面统一通过 [display] / [toString] 展示「code + message」。
class ApiException implements Exception {
  const ApiException(this.message, {this.code, this.statusCode});

  final String message;
  final String? code;
  final int? statusCode;

  /// 面向用户的展示文本，格式 `[SW-CARD-404] 卡片不存在`。
  String get display => code == null ? message : '[$code] $message';

  @override
  String toString() => display;
}

/// 从响应体解析统一错误 `{status, error_code, message}`（纯函数，便于单测）。
///
/// 兼容 FastAPI 校验错误（`detail` 字段）。
ApiException errorFromBody(Map<String, dynamic> body, {int? statusCode}) {
  final code = body['error_code'] as String?;
  final message = _firstMessage(body['message']) ?? _firstMessage(body['detail']);
  final resolvedStatus = statusCode ?? (code != null ? statusForCode(code) : null);
  return ApiException(
    message ?? '请求失败',
    code: code,
    statusCode: resolvedStatus,
  );
}

String? _firstMessage(dynamic value) {
  if (value is String && value.isNotEmpty) return value;
  return null;
}

/// 将 [DioException] 映射为统一的 [ApiException]。
///
/// 有响应体时优先解析 `{error_code, message}`；否则按 HTTP 状态映射
/// `SW-GENERIC-xxx`；无响应（连接失败）时给出友好提示。
ApiException apiExceptionFromDioException(DioException error) {
  final response = error.response;
  final statusCode = response?.statusCode;
  final data = response?.data;

  if (data is Map) {
    final body = <String, dynamic>{};
    data.forEach((key, value) => body['$key'] = value);
    final code = body['error_code'] as String?;
    final message =
        _firstMessage(body['message']) ?? _firstMessage(body['detail']);
    if (code != null || message != null) {
      return ApiException(
        message ?? '请求失败',
        code: code,
        statusCode: statusCode,
      );
    }
  }

  if (statusCode != null) {
    return ApiException(
      '请求失败（HTTP $statusCode）',
      code: genericCodeForStatus(statusCode),
      statusCode: statusCode,
    );
  }

  return ApiException(_connectionErrorMessage(error));
}

String _connectionErrorMessage(DioException error) {
  switch (error.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
      return '请求超时，请检查网络';
    case DioExceptionType.connectionError:
      return '无法连接服务器，请确认服务已启动';
    case DioExceptionType.cancel:
      return '请求已取消';
    default:
      return '网络请求失败：${error.message ?? error.type.name}';
  }
}

class ApiClient {
  ApiClient({Dio? dio, String? baseUrl})
      : _dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: baseUrl ?? ApiConfig.baseUrl,
                connectTimeout: const Duration(seconds: 5),
                receiveTimeout: const Duration(seconds: 30),
                sendTimeout: const Duration(seconds: 15),
                headers: {
                  if (ApiConfig.apiToken.isNotEmpty)
                    'Authorization': 'Bearer ${ApiConfig.apiToken}',
                },
              ),
            );

  final Dio _dio;

  String get baseUrl => ApiConfig.baseUrl;

  String wsUrl(String path) => ApiConfig.wsBaseUrl(path);

  Future<BootstrapStatus> getBootstrapStatus() async {
    final data = await _dataOf(_dio.get<dynamic>('/api/bootstrap/status'));
    return BootstrapStatus.fromJson(data);
  }

  Future<BootstrapActionResult> testBootstrap({
    required String provider,
    required String apiKey,
    required String baseUrl,
    String model = '',
  }) async {
    final data = await _dataOf(
      _dio.post<dynamic>(
        '/api/bootstrap/test',
        data: {
          'provider': provider,
          'api_key': apiKey,
          'base_url': baseUrl,
          'model': model,
        },
      ),
    );
    return BootstrapActionResult.fromJson(data);
  }

  Future<BootstrapActionResult> configureBootstrap({
    required String provider,
    required String apiKey,
    required String baseUrl,
    String model = '',
  }) async {
    final data = await _dataOf(
      _dio.post<dynamic>(
        '/api/bootstrap/configure',
        data: {
          'provider': provider,
          'api_key': apiKey,
          'base_url': baseUrl,
          'model': model,
        },
      ),
    );
    return BootstrapActionResult.fromJson(data);
  }

  /// 批量保存设置(写 .env 并即时生效, 无需重启)。
  Future<void> saveSettings(Map<String, String> updates) async {
    await _dataOf(_dio.post<dynamic>('/api/settings/batch', data: [
      for (final e in updates.entries) {'key': e.key, 'value': e.value},
    ]));
  }

  /// 获取指标(含 LLM token 用量)。
  Future<Map<String, dynamic>> getMetrics() async {
    return _dataOf(_dio.get<dynamic>('/api/metrics'));
  }

  Future<List<String>> listCategories() async {
    final data = await _dataOf(_dio.get<dynamic>('/api/categories'));
    final raw = data['categories'];
    if (raw is List) {
      return raw.map((e) => e.toString()).toList();
    }
    return const [];
  }

  /// 新建分类。
  Future<void> createCategory(String name) async {
    await _dataOf(_dio.post<dynamic>('/api/categories', data: {'name': name}));
  }

  /// 重命名分类(同步改该分类下所有卡片)。
  Future<void> renameCategory(String oldName, String newName) async {
    await _dataOf(_dio.put<dynamic>(
      '/api/categories',
      data: {'old_name': oldName, 'new_name': newName},
    ));
  }

  /// 删除分类(该分类下卡片归入「通用」)。
  ///
  /// 名称走 JSON body: 分类名含 `/`、`.` 等字符时路径参数会被
  /// 路由解码/规范化, 导致 404「接口不存在」。
  Future<void> deleteCategory(String name) async {
    await _dataOf(_dio.delete<dynamic>('/api/categories', data: {'name': name}));
  }

  Future<List<KnowledgeCard>> listCards({
    String? category,
    int page = 1,
    int limit = 200,
    String sort = 'created',
  }) async {
    final data = await _dataOf(
      _dio.get<dynamic>(
        '/api/cards',
        queryParameters: {
          if (category != null && category.isNotEmpty) 'category': category,
          'page': page,
          'limit': limit,
          'sort': sort,
        },
      ),
    );
    return _cardsFrom(data['cards']);
  }

  Future<KnowledgeCard?> getCard(String cardId) async {
    final data = await _dataOf(_dio.get<dynamic>('/api/cards/$cardId'));
    return KnowledgeCard.fromJson(data);
  }

  /// 手动创建卡片。
  Future<KnowledgeCard> createCard(Map<String, dynamic> payload) async {
    final data = await _dataOf(_dio.post<dynamic>('/api/cards', data: payload));
    return KnowledgeCard.fromJson(data);
  }

  /// 手动更新卡片。
  Future<KnowledgeCard> updateCard(
    String cardId,
    Map<String, dynamic> payload,
  ) async {
    final data = await _dataOf(
      _dio.put<dynamic>('/api/cards/$cardId', data: payload),
    );
    return KnowledgeCard.fromJson(data);
  }

  /// 删除卡片。
  Future<void> deleteCard(String cardId) async {
    await _dataOf(_dio.delete<dynamic>('/api/cards/$cardId'));
  }

  Future<List<KnowledgeCard>> searchCards(String query) async {
    final data = await _dataOf(
      _dio.get<dynamic>(
        '/api/cards/search',
        queryParameters: {'q': query},
      ),
    );
    return _cardsFrom(data['cards']);
  }

  /// 生成 Quiz(后端会保存为 quiz 卡片), 返回 (quiz_id, questions)。
  Future<({String quizId, List<QuizQuestion> questions})> generateQuiz(
      String cardId) async {
    final data = await _dataOf(
      _dio.post<dynamic>('/api/quiz/generate/$cardId'),
    );
    final raw = data['questions'];
    final questions = raw is List
        ? raw
            .whereType<Map<String, dynamic>>()
            .map(QuizQuestion.fromJson)
            .toList()
        : <QuizQuestion>[];
    return (
      quizId: data['quiz_id']?.toString() ?? '',
      questions: questions,
    );
  }

  Future<Map<String, dynamic>> gradeQuiz({
    required String cardId,
    String quizId = '',
    required List<Map<String, String>> answers,
  }) async {
    final data = await _dataOf(
      _dio.post<dynamic>(
        '/api/quiz/grade',
        data: {
          'card_id': cardId,
          if (quizId.isNotEmpty) 'quiz_id': quizId,
          'answers': answers,
        },
      ),
    );
    return data;
  }

  // ── Quiz 卡片(永久保存) ────────────────────────────────

  Future<List<QuizCard>> listQuizzes({String cardId = ''}) async {
    final data = await _dataOf(
      _dio.get<dynamic>(
        '/api/quizzes',
        queryParameters: {if (cardId.isNotEmpty) 'card_id': cardId},
      ),
    );
    final raw = data['quizzes'];
    if (raw is List) {
      return raw
          .whereType<Map<String, dynamic>>()
          .map(QuizCard.fromJson)
          .toList();
    }
    return const [];
  }

  Future<QuizCard> getQuiz(String quizId) async {
    final data = await _dataOf(_dio.get<dynamic>('/api/quizzes/$quizId'));
    return QuizCard.fromJson(data);
  }

  Future<QuizCard> createQuiz({
    required String title,
    List<String> cardIds = const [],
    required List<Map<String, dynamic>> questions,
    String source = 'agent',
  }) async {
    final data = await _dataOf(
      _dio.post<dynamic>(
        '/api/quizzes',
        data: {
          'title': title,
          'card_ids': cardIds,
          'questions': questions,
          'source': source,
        },
      ),
    );
    return QuizCard.fromJson(data);
  }

  Future<QuizCard> updateQuiz(
    String quizId, {
    String? title,
    List<String>? cardIds,
    List<Map<String, dynamic>>? questions,
    String? status,
    bool? submitted,
    bool? userEdited,
  }) async {
    final data = await _dataOf(
      _dio.put<dynamic>(
        '/api/quizzes/$quizId',
        data: {
          if (title != null) 'title': title,
          if (cardIds != null) 'card_ids': cardIds,
          if (questions != null) 'questions': questions,
          if (status != null) 'status': status,
          if (submitted != null) 'submitted': submitted,
          if (userEdited != null) 'user_edited': userEdited,
        },
      ),
    );
    return QuizCard.fromJson(data);
  }

  Future<void> deleteQuiz(String quizId) async {
    await _dataOf(_dio.delete<dynamic>('/api/quizzes/$quizId'));
  }

  List<KnowledgeCard> _cardsFrom(dynamic raw) {
    if (raw is List) {
      return raw
          .whereType<Map<String, dynamic>>()
          .map(KnowledgeCard.fromJson)
          .toList();
    }
    return const [];
  }

  /// 统一解析响应：DioException → ApiException；`status == error` → ApiException。
  /// 成功时返回顶层 `data`（无 `data` 时返回空 Map）。
  Future<Map<String, dynamic>> _dataOf(
    Future<Response<dynamic>> request,
  ) async {
    Response<dynamic> response;
    try {
      response = await request;
    } on DioException catch (e) {
      throw apiExceptionFromDioException(e);
    }
    final body = response.data;
    if (body is! Map) {
      return const <String, dynamic>{};
    }
    final map = <String, dynamic>{};
    body.forEach((key, value) => map['$key'] = value);
    if (map['status'] == 'error') {
      throw errorFromBody(map, statusCode: response.statusCode);
    }
    final data = map['data'];
    if (data is Map) {
      final result = <String, dynamic>{};
      data.forEach((key, value) => result['$key'] = value);
      return result;
    }
    return const <String, dynamic>{};
  }

  /// 上传文档并返回任务信息 {task_id, filename, storage_name, size}。
  Future<Map<String, dynamic>> uploadDocument(File file) async {
    // 用平台分隔符取文件名, 避免 file.uri.pathSegments 对中文路径
    // 在 Windows 上产生编码问题(multipart header 写入失败 → errno 22)。
    final separator = Platform.pathSeparator;
    final rawName = file.path.split(separator).last;
    // 文件名保留原始字符(后端按 UTF-8 解码), 但剔除可能破坏
    // Content-Disposition 的引号/控制字符。
    final safeName = rawName
        .replaceAll('"', '')
        .replaceAll(RegExp(r'[\x00-\x1f]'), '_')
        .trim();
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(
        file.path,
        filename: safeName.isEmpty ? 'upload' : safeName,
      ),
    });
    return _dataOf(
      _dio.post<dynamic>(
        '/api/upload',
        data: form,
        options: Options(
          contentType: 'multipart/form-data',
          sendTimeout: const Duration(seconds: 120),
        ),
      ),
    );
  }

  /// 查询导入任务状态 {task_id, status, message, progress, result}。
  Future<Map<String, dynamic>> uploadTaskStatus(String taskId) {
    return _dataOf(_dio.get<dynamic>('/api/upload/status/$taskId'));
  }

  /// 取消导入任务。
  Future<Map<String, dynamic>> cancelUploadTask(String taskId) {
    return _dataOf(_dio.post<dynamic>('/api/upload/cancel/$taskId'));
  }
}

/// 配对协议客户端封装（`POST /api/pair/verify {code, device_id}`）。
///
/// 该后端端点当前为待补项：404/501 时返回 `notImplemented=true` 并给出
/// 「服务端未启用配对」的友好提示，不向后端抛错。
class PairApi {
  PairApi({Dio? dio})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 5),
                receiveTimeout: const Duration(seconds: 15),
              ),
            );

  final Dio _dio;

  Future<PairResult> verify({
    required String baseUrl,
    required String code,
    required String deviceId,
  }) async {
    final url = '${_withoutTrailingSlash(baseUrl)}/api/pair/verify';
    int? statusCode;
    Map<String, dynamic>? body;
    String? dioMessage;
    try {
      final response = await _dio.post<dynamic>(
        url,
        data: {'code': code, 'device_id': deviceId},
      );
      statusCode = response.statusCode;
      final data = response.data;
      if (data is Map) {
        final map = <String, dynamic>{};
        data.forEach((key, value) => map['$key'] = value);
        body = map;
      }
    } on DioException catch (e) {
      statusCode = e.response?.statusCode;
      dioMessage = _connectionErrorMessage(e);
    }
    return pairVerifyResult(
      statusCode: statusCode,
      body: body,
      dioMessage: dioMessage,
    );
  }
}

/// 将 verify 端点响应映射为 [PairResult]（纯函数，便于单测）。
PairResult pairVerifyResult({
  int? statusCode,
  Map<String, dynamic>? body,
  String? dioMessage,
}) {
  // 后端尚未实现配对端点：404（路由不存在）/ 501（未实现）。
  if (statusCode == 404 || statusCode == 501) {
    return const PairResult(
      ok: false,
      message: '服务端未启用配对',
      notImplemented: true,
    );
  }
  if (body != null) {
    if (body['status'] == 'error') {
      final error = errorFromBody(body, statusCode: statusCode);
      return PairResult(
        ok: false,
        message: error.display,
        errorCode: error.code,
      );
    }
    return const PairResult(ok: true, message: '配对成功');
  }
  if (statusCode != null) {
    final code = genericCodeForStatus(statusCode);
    return PairResult(
      ok: false,
      message: '[$code] 服务返回 HTTP $statusCode',
      errorCode: code,
    );
  }
  return PairResult(ok: false, message: dioMessage ?? '无法连接服务器');
}

String _withoutTrailingSlash(String value) {
  return value.endsWith('/') ? value.substring(0, value.length - 1) : value;
}

/// 运行时服务器地址: 配对/手动配置后更新, 触发 apiClientProvider 重建
/// (新的 Dio baseUrl 指向电脑后端)。
final serverBaseUrlProvider = StateProvider<String?>((ref) => ServerConfig.baseUrl);

final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(baseUrl: ref.watch(serverBaseUrlProvider)),
);

final pairApiProvider = Provider<PairApi>((ref) => PairApi());
