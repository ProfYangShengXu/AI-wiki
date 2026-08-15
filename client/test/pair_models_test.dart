import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:studywiki_client/models/pair_models.dart';

void main() {
  group('PairCode', () {
    test('6 位纯数字合法', () {
      expect(PairCode.isValid('123456'), isTrue);
      expect(PairCode.isValid('000000'), isTrue);
    });

    test('空格与连字符可归一化', () {
      expect(PairCode.normalize('123 456'), '123456');
      expect(PairCode.normalize('123-456'), '123456');
      expect(PairCode.isValid('123 456'), isTrue);
      expect(PairCode.isValid('123-456'), isTrue);
    });

    test('非法输入拒绝', () {
      expect(PairCode.isValid('12345'), isFalse);
      expect(PairCode.isValid('1234567'), isFalse);
      expect(PairCode.isValid('abcdef'), isFalse);
      expect(PairCode.isValid('12a456'), isFalse);
      expect(PairCode.isValid(''), isFalse);
    });

    test('生成结果始终为 6 位数字（含前导零）', () {
      final code = PairCode.generate(random: Random(42));
      expect(code.length, 6);
      expect(PairCode.isValid(code), isTrue);
    });
  });

  group('generateDeviceId', () {
    test('返回 16 位十六进制', () {
      final id = generateDeviceId(random: Random(7));
      expect(id.length, 16);
      expect(RegExp(r'^[0-9a-f]{16}$').hasMatch(id), isTrue);
    });
  });

  group('PairPayload', () {
    test('encode/decode 往返', () {
      const payload = PairPayload(
        code: '123456',
        server: 'http://192.168.1.10:8000',
        deviceId: '1a2b3c4d5e6f7081',
      );
      final encoded = payload.encode();
      expect(encoded, contains('studywiki-pair'));
      final decoded = PairPayload.decode(encoded);
      expect(decoded, isNotNull);
      expect(decoded!.code, '123456');
      expect(decoded.server, 'http://192.168.1.10:8000');
      expect(decoded.deviceId, '1a2b3c4d5e6f7081');
    });

    test('非本协议内容返回 null', () {
      expect(PairPayload.decode('{"type":"other"}'), isNull);
      expect(PairPayload.decode('not json'), isNull);
    });

    test('缺字段返回 null', () {
      expect(PairPayload.decode('{"type":"studywiki-pair","code":"1"}'), isNull);
    });
  });
}
