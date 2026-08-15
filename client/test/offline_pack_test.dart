import 'package:flutter_test/flutter_test.dart';
import 'package:studywiki_client/models/knowledge_card.dart';
import 'package:studywiki_client/models/offline_pack.dart';

void main() {
  group('OfflinePack', () {
    test('toJson/fromJson 往返', () {
      const pack = OfflinePack(
        cards: [
          KnowledgeCard(
            id: '1',
            title: 'CPU',
            content: '中央处理器',
            category: '硬件',
            aliases: ['中央处理器'],
          ),
          KnowledgeCard(id: '2', title: 'GPU', category: '硬件'),
        ],
        exportedAt: '2026-06-01T00:00:00Z',
        server: 'http://127.0.0.1:8000',
      );

      final json = pack.toJson();
      expect(json['format'], 'studywiki-offline-pack');
      expect(json['version'], 1);
      expect(json['card_count'], 2);

      final decoded = OfflinePack.fromJson(json);
      expect(decoded, isNotNull);
      expect(decoded!.cards.length, 2);
      expect(decoded.cards.first.title, 'CPU');
      expect(decoded.cards.first.aliases, ['中央处理器']);
    });

    test('非本格式返回 null', () {
      expect(OfflinePack.fromJson(const {'format': 'other'}), isNull);
    });

    test('cards 非列表时返回空列表', () {
      final pack = OfflinePack.fromJson(const {
        'format': 'studywiki-offline-pack',
        'version': 1,
        'cards': 'not-a-list',
      });
      expect(pack, isNotNull);
      expect(pack!.cards, isEmpty);
    });
  });

  group('offlinePackToMarkdown', () {
    test('渲染标题、分类与正文', () {
      const pack = OfflinePack(
        cards: [
          KnowledgeCard(
            id: '1',
            title: 'CPU',
            category: '硬件',
            content: '中央处理器',
            examples: ['例子'],
            questions: ['问题'],
          ),
        ],
        exportedAt: '2026-06-01T00:00:00Z',
        server: 'http://127.0.0.1:8000',
      );
      final md = offlinePackToMarkdown(pack);
      expect(md, contains('# StudyWiki 离线知识包'));
      expect(md, contains('## [硬件] CPU'));
      expect(md, contains('中央处理器'));
      expect(md, contains('### 案例'));
      expect(md, contains('### 复习问题'));
    });
  });

  group('QuizGradeRequest', () {
    test('toJson/fromJson 往返', () {
      const request = QuizGradeRequest(
        cardId: '1',
        answers: [
          {'question': 'Q1', 'answer': 'A1'},
        ],
        submittedAt: '2026-06-01T00:00:00Z',
      );
      final json = request.toJson();
      final decoded = QuizGradeRequest.fromJson(json);
      expect(decoded, isNotNull);
      expect(decoded!.cardId, '1');
      expect(decoded.answers.first['answer'], 'A1');
    });

    test('toSubmission 去除本地字段', () {
      const request = QuizGradeRequest(
        cardId: '1',
        answers: [
          {'question': 'Q1', 'answer': 'A1'},
        ],
        submittedAt: '2026-06-01T00:00:00Z',
      );
      final submission = request.toSubmission();
      expect(submission.containsKey('submitted_at'), isFalse);
      expect(submission['card_id'], '1');
    });

    test('缺 card_id 时返回 null', () {
      expect(
        QuizGradeRequest.fromJson(const {'answers': []}),
        isNull,
      );
    });
  });
}
