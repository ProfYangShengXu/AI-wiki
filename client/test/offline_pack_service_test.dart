import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:studywiki_client/core/api_client.dart';
import 'package:studywiki_client/models/knowledge_card.dart';
import 'package:studywiki_client/models/offline_pack.dart';
import 'package:studywiki_client/services/offline_pack_service.dart';

class _FakeApiClient extends ApiClient {
  _FakeApiClient({this.failGrades = false});

  final bool failGrades;
  int gradeCalls = 0;

  @override
  Future<Map<String, dynamic>> gradeQuiz({
    required String cardId,
    String quizId = '',
    required List<Map<String, String>> answers,
  }) async {
    gradeCalls++;
    if (failGrades) {
      throw const ApiException('无法连接服务器');
    }
    return {'card_id': cardId, 'results': const []};
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('缓存', () {
    test('savePack/loadPack 往返', () async {
      final service = OfflinePackService(api: _FakeApiClient());
      const pack = OfflinePack(
        cards: [KnowledgeCard(id: '1', title: 'CPU')],
        exportedAt: '2026-06-01T00:00:00Z',
        server: 'http://127.0.0.1:8000',
      );
      await service.savePack(pack);

      final loaded = await service.loadPack();
      expect(loaded, isNotNull);
      expect(loaded!.cards.length, 1);
      expect(loaded.cards.first.title, 'CPU');
    });

    test('无缓存时 loadPack 返回 null，hasCache 返回 false', () async {
      final service = OfflinePackService(api: _FakeApiClient());
      expect(await service.loadPack(), isNull);
      expect(await service.hasCache(), isFalse);
      expect(await service.cachedCards(), isEmpty);
    });

    test('缓存损坏时返回 null', () async {
      SharedPreferences.setMockInitialValues({
        OfflinePackService.packCacheKey: 'not-json{{',
      });
      final service = OfflinePackService(api: _FakeApiClient());
      expect(await service.loadPack(), isNull);
    });

    test('cachedCards 返回缓存卡片列表', () async {
      final service = OfflinePackService(api: _FakeApiClient());
      await service.savePack(
        const OfflinePack(
          cards: [
            KnowledgeCard(id: '1', title: 'CPU'),
            KnowledgeCard(id: '2', title: 'GPU'),
          ],
        ),
      );
      final cards = await service.cachedCards();
      expect(cards.length, 2);
      expect(await service.hasCache(), isTrue);
    });
  });

  group('Quiz 回传队列', () {
    test('enqueue/pending 往返', () async {
      final service = OfflinePackService(api: _FakeApiClient());
      await service.enqueueGrade(
        const QuizGradeRequest(
          cardId: '1',
          answers: [
            {'question': 'Q1', 'answer': 'A1'},
          ],
          submittedAt: '2026-06-01T00:00:00Z',
        ),
      );
      final pending = await service.pendingGrades();
      expect(pending.length, 1);
      expect(pending.first.cardId, '1');
    });

    test('flushPendingGrades 全部成功时清空队列', () async {
      final api = _FakeApiClient();
      final service = OfflinePackService(api: api);
      await service.enqueueGrade(
        const QuizGradeRequest(
          cardId: '1',
          answers: [
            {'question': 'Q1', 'answer': 'A1'},
          ],
          submittedAt: '',
        ),
      );
      await service.enqueueGrade(
        const QuizGradeRequest(
          cardId: '2',
          answers: [
            {'question': 'Q2', 'answer': 'A2'},
          ],
          submittedAt: '',
        ),
      );

      final result = await service.flushPendingGrades();
      expect(result.sent, 2);
      expect(result.failed, 0);
      expect(result.remaining, 0);
      expect(api.gradeCalls, 2);
      expect(await service.pendingGrades(), isEmpty);
    });

    test('flushPendingGrades 失败时保留队列', () async {
      final api = _FakeApiClient(failGrades: true);
      final service = OfflinePackService(api: api);
      await service.enqueueGrade(
        const QuizGradeRequest(
          cardId: '1',
          answers: [
            {'question': 'Q1', 'answer': 'A1'},
          ],
          submittedAt: '',
        ),
      );

      final result = await service.flushPendingGrades();
      expect(result.sent, 0);
      expect(result.failed, 1);
      expect(result.remaining, 1);
      expect(await service.pendingGrades(), hasLength(1));
    });

    test('clearPendingGrades 清空队列', () async {
      final service = OfflinePackService(api: _FakeApiClient());
      await service.enqueueGrade(
        const QuizGradeRequest(
          cardId: '1',
          answers: [
            {'question': 'Q1', 'answer': 'A1'},
          ],
          submittedAt: '',
        ),
      );
      await service.clearPendingGrades();
      expect(await service.pendingGrades(), isEmpty);
    });
  });
}
