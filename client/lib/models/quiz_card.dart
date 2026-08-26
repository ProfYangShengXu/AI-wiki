/// Quiz 卡片模型 — Quiz 页永久保存的测验条目。
library;

/// 单道题(含参考答案/用户答案/评分)。
class QuizQuestionItem {
  const QuizQuestionItem({
    required this.question,
    this.refAnswer = '',
    this.userAnswer = '',
    this.score,
    this.comment = '',
  });

  final String question;
  final String refAnswer;
  final String userAnswer;
  final int? score;
  final String comment;

  bool get graded => score != null;

  factory QuizQuestionItem.fromJson(Map<String, dynamic> json) {
    return QuizQuestionItem(
      question: json['question'] as String? ?? '',
      refAnswer: json['ref_answer'] as String? ?? '',
      userAnswer: json['user_answer'] as String? ?? '',
      score: json['score'] as int?,
      comment: json['comment'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'question': question,
        'ref_answer': refAnswer,
        'user_answer': userAnswer,
        if (score != null) 'score': score,
        'comment': comment,
      };

  QuizQuestionItem copyWith({
    String? question,
    String? refAnswer,
    String? userAnswer,
    int? score,
    String? comment,
  }) {
    return QuizQuestionItem(
      question: question ?? this.question,
      refAnswer: refAnswer ?? this.refAnswer,
      userAnswer: userAnswer ?? this.userAnswer,
      score: score ?? this.score,
      comment: comment ?? this.comment,
    );
  }
}

/// Quiz 卡片完整记录。
class QuizCard {
  const QuizCard({
    required this.id,
    required this.title,
    required this.cardIds,
    required this.questions,
    required this.status,
    required this.submitted,
    required this.userEdited,
    required this.source,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String title;
  final List<String> cardIds;
  final List<QuizQuestionItem> questions;
  final String status; // draft | submitted | graded
  final bool submitted;
  final bool userEdited;
  final String source; // agent | quizpage | exam
  final String createdAt;
  final String updatedAt;

  bool get graded => status == 'graded';
  int get totalScore =>
      questions.fold(0, (sum, q) => sum + (q.score ?? 0));
  int get maxScore => questions.length * 10;

  String get statusLabel {
    switch (status) {
      case 'submitted':
        return '已提交';
      case 'graded':
        return '已评分';
      default:
        return '未提交';
    }
  }

  factory QuizCard.fromJson(Map<String, dynamic> json) {
    final rawQuestions = json['questions'];
    return QuizCard(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      cardIds: (json['card_ids'] as List?)?.map((e) => e.toString()).toList() ?? const [],
      questions: rawQuestions is List
          ? rawQuestions
              .whereType<Map<String, dynamic>>()
              .map(QuizQuestionItem.fromJson)
              .toList()
          : const [],
      status: json['status'] as String? ?? 'draft',
      submitted: json['submitted'] as bool? ?? false,
      userEdited: json['user_edited'] as bool? ?? false,
      source: json['source'] as String? ?? 'agent',
      createdAt: json['created_at'] as String? ?? '',
      updatedAt: json['updated_at'] as String? ?? '',
    );
  }
}
