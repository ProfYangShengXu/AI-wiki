import 'knowledge_card.dart';

/// 离线知识包格式（JSON，结构自定并在此文档化）。
///
/// 顶层结构：
/// ```json
/// {
///   "format": "studywiki-offline-pack",
///   "version": 1,
///   "exported_at": "2026-06-01T12:00:00Z",
///   "server": "http://127.0.0.1:8000",
///   "card_count": 3,
///   "cards": [ ...CardResponse... ]
/// }
/// ```
///
/// - `cards` 每项与后端 `CardResponse` 兼容（见 [KnowledgeCard.toJson]）。
/// - Markdown 版本由 [offlinePackToMarkdown] 生成，用于人类可读/编辑的副本。
class OfflinePack {
  const OfflinePack({
    required this.cards,
    this.exportedAt = '',
    this.server = '',
  });

  static const String format = 'studywiki-offline-pack';
  static const int version = 1;

  final List<KnowledgeCard> cards;
  final String exportedAt;
  final String server;

  int get cardCount => cards.length;

  Map<String, dynamic> toJson() {
    return {
      'format': format,
      'version': version,
      'exported_at': exportedAt,
      'server': server,
      'card_count': cards.length,
      'cards': cards.map((c) => c.toJson()).toList(),
    };
  }

  static OfflinePack? fromJson(Map<String, dynamic> json) {
    if (json['format'] != format) return null;
    final rawCards = json['cards'];
    final cards = <KnowledgeCard>[];
    if (rawCards is List) {
      for (final item in rawCards) {
        if (item is Map<String, dynamic>) {
          cards.add(KnowledgeCard.fromJson(item));
        }
      }
    }
    return OfflinePack(
      cards: cards,
      exportedAt: json['exported_at'] as String? ?? '',
      server: json['server'] as String? ?? '',
    );
  }
}

/// 将离线包渲染为 Markdown（人类可读副本）。
///
/// 结构：
/// ```markdown
/// # StudyWiki 离线知识包
/// > 导出时间 / 服务器 / 卡片数
///
/// ## [分类] 标题
/// 别名 / 正文 / 案例 / 复习问题 / 来源
/// ```
String offlinePackToMarkdown(OfflinePack pack) {
  final buffer = StringBuffer()
    ..writeln('# StudyWiki 离线知识包')
    ..writeln()
    ..writeln('> 导出时间: ${pack.exportedAt.isEmpty ? '未知' : pack.exportedAt}')
    ..writeln('> 服务器: ${pack.server.isEmpty ? '未知' : pack.server}')
    ..writeln('> 卡片数: ${pack.cardCount}')
    ..writeln();

  for (final card in pack.cards) {
    buffer
      ..writeln('## [${card.category}] ${card.title}')
      ..writeln();
    if (card.aliases.isNotEmpty) {
      buffer.writeln('别名: ${card.aliases.join(' / ')}');
    }
    if (card.content.isNotEmpty) {
      buffer
        ..writeln()
        ..writeln(card.content);
    }
    if (card.examples.isNotEmpty) {
      buffer
        ..writeln()
        ..writeln('### 案例');
      for (final e in card.examples) {
        buffer.writeln('- $e');
      }
    }
    if (card.questions.isNotEmpty) {
      buffer
        ..writeln()
        ..writeln('### 复习问题');
      for (final q in card.questions) {
        buffer.writeln('- $q');
      }
    }
    if (card.sourceFile.isNotEmpty) {
      buffer
        ..writeln()
        ..writeln('来源: ${card.sourceFile} 第 ${card.sourcePage} 页');
    }
    buffer
      ..writeln()
      ..writeln();
  }
  return buffer.toString().trimRight();
}

/// 一条待回传的 Quiz 评分请求（离线队列元素）。
class QuizGradeRequest {
  const QuizGradeRequest({
    required this.cardId,
    required this.answers,
    required this.submittedAt,
  });

  final String cardId;

  /// 与后端 `QuizSubmission.answers` 一致：`{"question": ..., "answer": ...}`。
  final List<Map<String, String>> answers;
  final String submittedAt;

  Map<String, dynamic> toJson() {
    return {
      'card_id': cardId,
      'answers': answers,
      'submitted_at': submittedAt,
    };
  }

  static QuizGradeRequest? fromJson(Map<String, dynamic> json) {
    final cardId = json['card_id'];
    if (cardId is! String || cardId.isEmpty) return null;
    final rawAnswers = json['answers'];
    final answers = <Map<String, String>>[];
    if (rawAnswers is List) {
      for (final item in rawAnswers) {
        if (item is Map) {
          answers.add({
            'question': item['question']?.toString() ?? '',
            'answer': item['answer']?.toString() ?? '',
          });
        }
      }
    }
    return QuizGradeRequest(
      cardId: cardId,
      answers: answers,
      submittedAt: json['submitted_at'] as String? ?? '',
    );
  }

  /// 构造提交给 `POST /api/quiz/grade` 的请求体（不含客户端本地字段）。
  Map<String, dynamic> toSubmission() {
    return {'card_id': cardId, 'answers': answers};
  }
}
