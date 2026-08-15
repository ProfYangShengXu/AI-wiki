class KnowledgeCard {
  const KnowledgeCard({
    required this.id,
    required this.title,
    this.aliases = const [],
    this.content = '',
    this.examples = const [],
    this.questions = const [],
    this.category = '未分类',
    this.sourceFile = '',
    this.sourcePage = 0,
    this.relatedCards = const [],
  });

  final String id;
  final String title;
  final List<String> aliases;
  final String content;
  final List<String> examples;
  final List<String> questions;
  final String category;
  final String sourceFile;
  final int sourcePage;
  final List<String> relatedCards;

  factory KnowledgeCard.fromJson(Map<String, dynamic> json) {
    return KnowledgeCard(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      aliases: _stringList(json['aliases']),
      content: json['content'] as String? ?? '',
      examples: _stringList(json['examples']),
      questions: _stringList(json['questions']),
      category: json['category'] as String? ?? '未分类',
      sourceFile: json['source_file'] as String? ?? '',
      sourcePage: json['source_page'] as int? ?? 0,
      relatedCards: _stringList(json['related_cards']),
    );
  }

  /// 序列化为与后端 `CardResponse` 兼容的 JSON（供离线包导出使用）。
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'aliases': aliases,
      'content': content,
      'examples': examples,
      'questions': questions,
      'category': category,
      'source_file': sourceFile,
      'source_page': sourcePage,
      'related_cards': relatedCards,
    };
  }

  static List<String> _stringList(dynamic value) {
    if (value is List) {
      return value.map((e) => e.toString()).toList();
    }
    return const [];
  }
}

class QuizQuestion {
  const QuizQuestion({required this.question, this.refAnswer = ''});

  final String question;
  final String refAnswer;

  factory QuizQuestion.fromJson(Map<String, dynamic> json) {
    return QuizQuestion(
      question: json['question'] as String? ?? '',
      refAnswer: json['ref_answer'] as String? ?? '',
    );
  }
}
