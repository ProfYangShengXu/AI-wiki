import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/bootstrap_models.dart';
import '../models/knowledge_card.dart';
import '../models/pair_models.dart';
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
  ApiClient({Dio? dio})
      : _dio = dio ??
            Dio(
              BaseOptions(
                baseUrl: ApiConfig.baseUrl,
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

  Future<List<String>> listCategories() async {
    final data = await _dataOf(_dio.get<dynamic>('/api/categories'));
    final raw = data['categories'];
    if (raw is List) {
      return raw.map((e) => e.toString()).toList();
    }
    return const [];
  }

  Future<List<KnowledgeCard>> listCards({
    String? category,
    int page = 1,
    int limit = 200,
  }) async {
    final data = await _dataOf(
      _dio.get<dynamic>(
        '/api/cards',
        queryParameters: {
          if (category != null && category.isNotEmpty) 'category': category,
          'page': page,
          'limit': limit,
        },
      ),
    );
    return _cardsFrom(data['cards']);
  }

  Future<KnowledgeCard?> getCard(String cardId) async {
    final data = await _dataOf(_dio.get<dynamic>('/api/cards/$cardId'));
    return KnowledgeCard.fromJson(data);
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

  Future<List<QuizQuestion>> generateQuiz(String cardId) async {
    final data = await _dataOf(
      _dio.post<dynamic>('/api/quiz/generate/$cardId'),
    );
    final raw = data['questions'];
    if (raw is List) {
      return raw
          .whereType<Map<String, dynamic>>()
          .map(QuizQuestion.fromJson)
          .toList();
    }
    return const [];
  }

  Future<Map<String, dynamic>> gradeQuiz({
    required String cardId,
    required List<Map<String, String>> answers,
  }) async {
    final data = await _dataOf(
      _dio.post<dynamic>(
        '/api/quiz/grade',
        data: {'card_id': cardId, 'answers': answers},
      ),
    );
    return data;
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
    final form = FormData.fromMap({
      'file': await MultipartFile.fromFile(
        file.path,
        filename: file.uri.pathSegments.last,
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

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

final pairApiProvider = Provider<PairApi>((ref) => PairApi());
