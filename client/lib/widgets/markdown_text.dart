import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

/// 轻量 Markdown 渲染组件（零外部依赖）。
///
/// 支持: ## 标题 / - 列表 / 1. 有序列表 / **粗体** / `行内代码`
///       [文本](链接) / 表格(简化成等宽行) / 段落。
/// 额外能力: 文本中出现的知识库卡片标题会渲染为可点击链接,
/// 点击后回调 [onCardTap], 实现「文字匹配的超链接跳转」。
class MarkdownText extends StatelessWidget {
  const MarkdownText(
    this.data, {
    super.key,
    this.cardTitles = const {},
    this.onCardTap,
    this.style,
  });

  final String data;
  final Set<String> cardTitles;
  final void Function(String title)? onCardTap;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final base = style ?? theme.textTheme.bodyMedium ?? const TextStyle();
    final blocks = _parseBlocks(data);
    final children = <Widget>[];
    for (final block in blocks) {
      children.add(block.build(context, base, cardTitles, onCardTap));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: children,
    );
  }
}

/// 解析后的块: 标题 / 列表 / 引用 / 表格 / 段落。
sealed class _MdBlock {
  Widget build(
    BuildContext context,
    TextStyle base,
    Set<String> cardTitles,
    void Function(String title)? onCardTap,
  );
}

class _HeadingBlock extends _MdBlock {
  _HeadingBlock(this.level, this.text);
  final int level;
  final String text;

  @override
  Widget build(BuildContext context, TextStyle base, Set<String> cardTitles,
      void Function(String title)? onCardTap) {
    final theme = Theme.of(context);
    final size = level == 1 ? 20.0 : (level == 2 ? 16.0 : 14.0);
    return Padding(
      padding: const EdgeInsets.only(top: 10, bottom: 4),
      child: Text(
        text,
        style: base.copyWith(
          fontSize: size,
          fontWeight: FontWeight.bold,
          color: theme.colorScheme.onSurface,
        ),
      ),
    );
  }
}

class _ListBlock extends _MdBlock {
  _ListBlock(this.items, {this.ordered = false});
  final List<String> items;
  final bool ordered;

  @override
  Widget build(BuildContext context, TextStyle base, Set<String> cardTitles,
      void Function(String title)? onCardTap) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < items.length; i++)
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  ordered ? '${i + 1}. ' : '• ',
                  style: base,
                ),
                Expanded(
                  child: _richText(
                    context,
                    items[i],
                    base,
                    cardTitles,
                    onCardTap,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _QuoteBlock extends _MdBlock {
  _QuoteBlock(this.text);
  final String text;

  @override
  Widget build(BuildContext context, TextStyle base, Set<String> cardTitles,
      void Function(String title)? onCardTap) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(6),
        border: Border(
          left: BorderSide(color: Theme.of(context).colorScheme.outline, width: 3),
        ),
      ),
      child: _richText(context, text, base, cardTitles, onCardTap),
    );
  }
}

class _TableBlock extends _MdBlock {
  _TableBlock(this.rows);
  final List<List<String>> rows;

  @override
  Widget build(BuildContext context, TextStyle base, Set<String> cardTitles,
      void Function(String title)? onCardTap) {
    if (rows.isEmpty) return const SizedBox.shrink();
    final cols = rows.map((r) => r.length).reduce((a, b) => a > b ? a : b);
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Table(
        columnWidths: {
          for (var c = 0; c < cols; c++) c: const IntrinsicColumnWidth(),
        },
        defaultVerticalAlignment: TableCellVerticalAlignment.middle,
        children: [
          for (var r = 0; r < rows.length; r++)
            TableRow(
              decoration: r == 0
                  ? BoxDecoration(
                      color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    )
                  : null,
              children: [
                for (var c = 0; c < cols; c++)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                    child: _richText(
                      context,
                      r < rows.length && c < rows[r].length ? rows[r][c] : '',
                      base.copyWith(
                        fontWeight: r == 0 ? FontWeight.bold : null,
                      ),
                      cardTitles,
                      onCardTap,
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}

class _ParagraphBlock extends _MdBlock {
  _ParagraphBlock(this.text);
  final String text;

  @override
  Widget build(BuildContext context, TextStyle base, Set<String> cardTitles,
      void Function(String title)? onCardTap) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 4),
      child: _richText(context, text, base, cardTitles, onCardTap),
    );
  }
}

/// 行内渲染: **粗体** / `代码` / [文本](链接) / 卡片标题链接。
Widget _richText(
  BuildContext context,
  String text,
  TextStyle base,
  Set<String> cardTitles,
  void Function(String title)? onCardTap,
) {
  final theme = Theme.of(context);
  final spans = <TextSpan>[];
  final plain = RegExp(r'(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))');
  var last = 0;
  for (final m in plain.allMatches(text)) {
    if (m.start > last) {
      spans.addAll(
        _plainSpans(text.substring(last, m.start), base, cardTitles, onCardTap,
            theme.colorScheme),
      );
    }
    final token = m.group(0)!;
    if (token.startsWith('**')) {
      spans.add(TextSpan(
        text: token.substring(2, token.length - 2),
        style: base.copyWith(fontWeight: FontWeight.bold),
      ));
    } else if (token.startsWith('`')) {
      spans.add(TextSpan(
        text: token.substring(1, token.length - 1),
        style: base.copyWith(
          fontFamily: 'monospace',
          backgroundColor: theme.colorScheme.surfaceContainerHighest,
        ),
      ));
    } else {
      final linkMatch = RegExp(r'^\[([^\]]+)\]\(([^)]+)\)$').firstMatch(token);
      final label = linkMatch?.group(1) ?? token;
      final target = linkMatch?.group(2);
      spans.add(TextSpan(
        text: label,
        style: base.copyWith(color: theme.colorScheme.primary),
        recognizer: TapGestureRecognizer()
          ..onTap = () {
            if (target != null && target.startsWith('card:')) {
              onCardTap?.call(target.substring(5));
            }
          },
      ));
    }
    last = m.end;
  }
  if (last < text.length) {
    spans.addAll(
      _plainSpans(text.substring(last), base, cardTitles, onCardTap,
          theme.colorScheme),
    );
  }
  if (spans.isEmpty) {
    spans.add(const TextSpan(text: ''));
  }
  return Text.rich(TextSpan(style: base, children: spans));
}

List<TextSpan> _plainSpans(
  String text,
  TextStyle base,
  Set<String> cardTitles,
  void Function(String title)? onCardTap,
  ColorScheme theme,
) {
  if (cardTitles.isEmpty || onCardTap == null || text.isEmpty) {
    return [TextSpan(text: text)];
  }
  // 文本内任意位置匹配卡片标题 → 链接 (按标题长度降序, 避免短标题
  // 先匹配吃掉长标题的前缀)。标题出现多次也全部链接化。
  final sorted = cardTitles.toList()
    ..sort((a, b) => b.length.compareTo(a.length));
  final spans = <TextSpan>[];
  var cursor = 0;
  while (cursor < text.length) {
    String? matchedTitle;
    var matchStart = -1;
    var matchEnd = -1;
    for (final title in sorted) {
      final idx = text.indexOf(title, cursor);
      if (idx >= 0 && (matchStart < 0 || idx < matchStart)) {
        matchStart = idx;
        matchEnd = idx + title.length;
        matchedTitle = title;
      }
    }
    if (matchedTitle == null || matchStart < 0) {
      // 剩余无匹配
      if (cursor < text.length) {
        spans.add(TextSpan(text: text.substring(cursor)));
      }
      break;
    }
    if (matchStart > cursor) {
      spans.add(TextSpan(text: text.substring(cursor, matchStart)));
    }
    final title = matchedTitle;
    spans.add(TextSpan(
      text: title,
      style: base.copyWith(color: theme.primary),
      recognizer: TapGestureRecognizer()..onTap = () => onCardTap(title),
    ));
    cursor = matchEnd;
  }
  if (spans.isEmpty) {
    spans.add(TextSpan(text: text));
  }
  return spans;
}

/// 块级解析: 按行分组为标题 / 列表 / 引用 / 表格 / 段落。
List<_MdBlock> _parseBlocks(String raw) {
  final blocks = <_MdBlock>[];
  final lines = raw.replaceAll('\r\n', '\n').split('\n');
  var i = 0;
  while (i < lines.length) {
    final line = lines[i].trimRight();
    final trimmed = line.trim();

    if (trimmed.isEmpty) {
      i++;
      continue;
    }
    // 标题
    final heading = RegExp(r'^(#{1,6})\s+(.+)$').firstMatch(trimmed);
    if (heading != null) {
      blocks.add(_HeadingBlock(heading.group(1)!.length, heading.group(2)!));
      i++;
      continue;
    }
    // 无序列表 (连续收集)
    if (RegExp(r'^[-*+]\s+').hasMatch(trimmed)) {
      final items = <String>[];
      while (i < lines.length &&
          RegExp(r'^[-*+]\s+').hasMatch(lines[i].trim())) {
        items.add(lines[i].trim().replaceFirst(RegExp(r'^[-*+]\s+'), ''));
        i++;
      }
      blocks.add(_ListBlock(items));
      continue;
    }
    // 有序列表
    if (RegExp(r'^\d+\.\s+').hasMatch(trimmed)) {
      final items = <String>[];
      while (i < lines.length &&
          RegExp(r'^\d+\.\s+').hasMatch(lines[i].trim())) {
        items.add(lines[i].trim().replaceFirst(RegExp(r'^\d+\.\s+'), ''));
        i++;
      }
      blocks.add(_ListBlock(items, ordered: true));
      continue;
    }
    // 引用
    if (trimmed.startsWith('>')) {
      final quoteLines = <String>[];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.add(lines[i].trim().replaceFirst(RegExp(r'^>\s?'), ''));
        i++;
      }
      blocks.add(_QuoteBlock(quoteLines.join(' ')));
      continue;
    }
    // 表格: 以 | 开头且下一行是分隔行 (|---|)
    if (trimmed.startsWith('|') && i + 1 < lines.length) {
      final sepMatch = RegExp(r'^\|[\s:|-]+\|?$').hasMatch(lines[i + 1].trim());
      if (sepMatch) {
        final rows = <List<String>>[];
        final header = _splitTableRow(trimmed);
        i += 2; // 跳过表头和分隔行
        while (i < lines.length && lines[i].trim().startsWith('|')) {
          rows.add(_splitTableRow(lines[i].trim()));
          i++;
        }
        blocks.add(_TableBlock([header, ...rows]));
        continue;
      }
    }
    // 段落 (连续普通行合并)
    final paraLines = <String>[trimmed];
    i++;
    while (i < lines.length) {
      final next = lines[i].trim();
      if (next.isEmpty ||
          RegExp(r'^(#{1,6})\s+|^[-*+]\s+|^\d+\.\s+|^>|^\|').hasMatch(next)) {
        break;
      }
      paraLines.add(next);
      i++;
    }
    blocks.add(_ParagraphBlock(paraLines.join(' ')));
  }
  return blocks;
}

List<String> _splitTableRow(String row) {
  final inner = row.trim().replaceFirst(RegExp(r'^\|'), '').replaceFirst(RegExp(r'\|$'), '');
  return inner.split('|').map((c) => c.trim()).toList();
}
