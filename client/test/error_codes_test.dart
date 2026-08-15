import 'package:flutter_test/flutter_test.dart';
import 'package:studywiki_client/core/error_codes.dart';

void main() {
  group('statusForCode', () {
    test('数字后缀直接作为状态码', () {
      expect(statusForCode('SW-CARD-404'), 404);
      expect(statusForCode('SW-QUIZ-500'), 500);
      expect(statusForCode('SW-AUTH-001'), 1);
    });

    test('非数字后缀按映射表回退', () {
      expect(statusForCode('SW-BOOTSTRAP-UPSTREAM'), 502);
      expect(statusForCode('SW-BOOTSTRAP-TIMEOUT'), 504);
      expect(statusForCode('SW-BOOTSTRAP-NETWORK'), 503);
    });

    test('未知后缀回退 500', () {
      expect(statusForCode('SW-FOO-BAR'), 500);
    });
  });

  group('genericCodeForStatus', () {
    test('已知状态码映射到 SW-GENERIC-xxx', () {
      expect(genericCodeForStatus(404), ErrorCodes.swGeneric404);
      expect(genericCodeForStatus(500), ErrorCodes.swGeneric500);
      expect(genericCodeForStatus(422), ErrorCodes.swGeneric422);
    });

    test('未知状态码回退占位格式', () {
      expect(genericCodeForStatus(418), 'SW-GENERIC-418');
    });
  });

  group('ErrorCodes 常量', () {
    test('与后端主要错误码同步', () {
      expect(ErrorCodes.all, contains(ErrorCodes.swAuth001));
      expect(ErrorCodes.all, contains(ErrorCodes.swCard404));
      expect(ErrorCodes.all, contains(ErrorCodes.swQuiz500));
      expect(ErrorCodes.all, contains(ErrorCodes.swBootstrapUpstream));
      expect(ErrorCodes.all, contains(ErrorCodes.swGeneric503));
    });

    test('describe 返回中文说明，未知码返回原文', () {
      expect(ErrorCodes.describe(ErrorCodes.swCard404), '卡片不存在');
      expect(ErrorCodes.describe('SW-UNKNOWN-999'), 'SW-UNKNOWN-999');
    });
  });
}
