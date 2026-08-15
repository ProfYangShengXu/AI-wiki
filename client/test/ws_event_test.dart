import 'package:flutter_test/flutter_test.dart';
import 'package:studywiki_client/models/ws_event.dart';

void main() {
  group('WsEvent.parse', () {
    test('解析 llm.delta', () {
      final event = WsEvent.parse(
        '{"type":"llm.delta","data":{"delta":"你好","session_id":"s1"}}',
      );
      expect(event, isNotNull);
      expect(event!.type, WsEvent.typeLlmDelta);
      expect(event.delta, '你好');
      expect(event.sessionId, 's1');
    });

    test('解析 tool.called / tool.result', () {
      final called = WsEvent.parse(
        '{"type":"tool.called","data":{"tool":"delete_card","args":{"card_id":"1"}}}',
      );
      expect(called!.tool, 'delete_card');
      expect(called.toolArgs['card_id'], '1');

      final result = WsEvent.parse(
        '{"type":"tool.result","data":{"tool":"delete_card","ok":true,"summary":"已删除"}}',
      );
      expect(result!.toolOk, isTrue);
      expect(result.toolSummary, '已删除');
    });

    test('解析 approval_required', () {
      final event = WsEvent.parse(
        '{"type":"approval_required","data":{"approval_id":"a1","tool":"clear_kb"}}',
      );
      expect(event!.type, WsEvent.typeApprovalRequired);
      expect(event.approvalId, 'a1');
      expect(event.tool, 'clear_kb');
    });

    test('解析 session 状态事件', () {
      final started = WsEvent.parse(
        '{"type":"session.started","data":{"session_id":"s1"}}',
      );
      expect(started!.sessionId, 's1');
      final done = WsEvent.parse('{"type":"session.done"}');
      expect(done!.type, WsEvent.typeSessionDone);
    });

    test('解析旧版 response/progress', () {
      final response = WsEvent.parse('{"type":"response","content":"回答"}');
      expect(response!.type, WsEvent.typeResponse);
      expect(response.content, '回答');

      final progress = WsEvent.parse(
        '{"type":"progress","data":{"stage":"thinking"}}',
      );
      expect(progress!.stage, 'thinking');
    });

    test('非法输入返回 null', () {
      expect(WsEvent.parse('not json'), isNull);
      expect(WsEvent.parse('{"no_type":1}'), isNull);
      expect(WsEvent.parse('123'), isNull);
    });
  });

  group('buildApproval', () {
    test('构造带 data 包裹的审批回执', () {
      final raw = WsEvent.buildApproval('a1', true);
      final parsed = WsEvent.parse(raw);
      expect(parsed!.type, 'approval');
      expect(parsed.approvalId, 'a1');
      expect(parsed.data['approved'], isTrue);
    });
  });
}
