import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:studywiki_client/core/api_client.dart';
import 'package:studywiki_client/models/pair_models.dart';

void main() {
  group('errorFromBody', () {
    test('解析统一错误体 {status, error_code, message}', () {
      final error = errorFromBody(const {
        'status': 'error',
        'error_code': 'SW-CARD-404',
        'message': '卡片不存在',
      });
      expect(error.code, 'SW-CARD-404');
      expect(error.message, '卡片不存在');
      expect(error.statusCode, 404);
      expect(error.display, '[SW-CARD-404] 卡片不存在');
    });

    test('无 error_code 时仅展示 message', () {
      final error = errorFromBody(const {
        'status': 'error',
        'message': '请求失败',
      });
      expect(error.code, isNull);
      expect(error.display, '请求失败');
    });

    test('兼容 FastAPI detail 字段', () {
      final error = errorFromBody(const {'detail': '请填写有效的 API Key'});
      expect(error.message, '请填写有效的 API Key');
      expect(error.code, isNull);
    });
  });

  group('apiExceptionFromDioException', () {
    test('从响应体解析 error_code/message', () {
      final response = Response<dynamic>(
        requestOptions: RequestOptions(path: '/api/cards/1'),
        statusCode: 404,
        data: const {
          'status': 'error',
          'error_code': 'SW-CARD-404',
          'message': '卡片不存在',
        },
      );
      final error = apiExceptionFromDioException(
        DioException(
          requestOptions: RequestOptions(path: '/api/cards/1'),
          response: response,
        ),
      );
      expect(error.code, 'SW-CARD-404');
      expect(error.message, '卡片不存在');
    });

    test('无响应体时按状态码映射 SW-GENERIC', () {
      final response = Response<dynamic>(
        requestOptions: RequestOptions(path: '/x'),
        statusCode: 500,
        data: null,
      );
      final error = apiExceptionFromDioException(
        DioException(
          requestOptions: RequestOptions(path: '/x'),
          response: response,
        ),
      );
      expect(error.code, 'SW-GENERIC-500');
    });

    test('连接失败时给出友好提示', () {
      final error = apiExceptionFromDioException(
        DioException(
          requestOptions: RequestOptions(path: '/x'),
          type: DioExceptionType.connectionError,
        ),
      );
      expect(error.code, isNull);
      expect(error.message, contains('无法连接服务器'));
    });
  });

  group('pairVerifyResult', () {
    test('404 视为服务端未启用配对', () {
      final result = pairVerifyResult(statusCode: 404);
      expect(result.ok, isFalse);
      expect(result.notImplemented, isTrue);
      expect(result.message, '服务端未启用配对');
    });

    test('501 视为服务端未启用配对', () {
      final result = pairVerifyResult(statusCode: 501);
      expect(result.notImplemented, isTrue);
    });

    test('status=error 时携带 code+message', () {
      final result = pairVerifyResult(
        statusCode: 401,
        body: const {
          'status': 'error',
          'error_code': 'SW-AUTH-001',
          'message': '未授权',
        },
      );
      expect(result.ok, isFalse);
      expect(result.errorCode, 'SW-AUTH-001');
      expect(result.message, '[SW-AUTH-001] 未授权');
    });

    test('成功响应返回 ok', () {
      final result = pairVerifyResult(
        statusCode: 200,
        body: const {'status': 'success', 'data': {}},
      );
      expect(result.ok, isTrue);
      expect(result.message, '配对成功');
    });

    test('无响应体时按状态码给通用错误', () {
      final result = pairVerifyResult(statusCode: 500);
      expect(result.ok, isFalse);
      expect(result.errorCode, 'SW-GENERIC-500');
    });
  });

  group('PairResult', () {
    test('字段可读', () {
      const result = PairResult(ok: true, message: '配对成功');
      expect(result.ok, isTrue);
      expect(result.notImplemented, isFalse);
    });
  });
}
