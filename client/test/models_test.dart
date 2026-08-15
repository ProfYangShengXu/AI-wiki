import 'package:flutter_test/flutter_test.dart';
import 'package:studywiki_client/models/bootstrap_models.dart';
import 'package:studywiki_client/models/knowledge_card.dart';

void main() {
  group('BootstrapStatus', () {
    test('parses required status without exposing raw key', () {
      final status = BootstrapStatus.fromJson(const {
        'required': true,
        'provider': 'deepseek',
        'has_key': false,
        'key_tail': '',
        'base_url': 'https://api.deepseek.com',
      });

      expect(status.required, isTrue);
      expect(status.provider, 'deepseek');
      expect(status.keyTail, '');
    });

    test('parses configured status', () {
      final status = BootstrapStatus.fromJson(const {
        'required': false,
        'provider': 'openai',
        'has_key': true,
        'key_tail': 'sk-...abcd',
        'base_url': 'https://api.openai.com/v1',
      });

      expect(status.required, isFalse);
      expect(status.keyTail, 'sk-...abcd');
    });
  });

  group('KnowledgeCard', () {
    test('parses card lists', () {
      final card = KnowledgeCard.fromJson(const {
        'id': '1',
        'title': 'CPU',
        'aliases': ['中央处理器'],
        'examples': ['例1'],
        'questions': ['问1'],
        'category': '硬件',
      });

      expect(card.id, '1');
      expect(card.title, 'CPU');
      expect(card.aliases, ['中央处理器']);
    });
  });
}
