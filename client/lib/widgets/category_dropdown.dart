import 'package:flutter/material.dart';

/// 分类下拉选择器 — 圆角深灰底、浅灰字、自带滚动条。
///
/// 基于 Material 3 的 [DropdownMenu] 实现:
/// - 按钮本体圆角深灰底 + 浅灰字, 深浅色模式统一;
/// - 菜单圆角深灰底, 内容超出 [menuHeight] 时自动出现滚动条;
/// - 外部状态通过 `key: ValueKey(selection)` 强制同步
///   ([DropdownMenu.initialSelection] 只在首次 build 生效)。
class CategoryDropdown extends StatelessWidget {
  const CategoryDropdown({
    super.key,
    required this.value,
    required this.onChanged,
    required this.categories,
    this.includeAll = true,
    this.hint = '分类',
  });

  /// 当前选中分类; null 表示「全部分类」(仅在 [includeAll] 时有效)。
  final String? value;

  /// 选中回调; 传入 null 表示选择了「全部分类」。
  final ValueChanged<String?> onChanged;

  final List<String> categories;

  /// 是否在列表顶部提供「全部分类」选项。
  final bool includeAll;

  final String hint;

  /// 「全部分类」哨兵值 — [DropdownMenuEntry.value] 不允许为 null。
  static const String _all = '__ALL__';

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final current = value ?? _all;
    // 深灰底 / 浅灰字 — 深浅色模式统一风格, 深色模式略深一档
    final bg = dark ? const Color(0xFF23262E) : const Color(0xFF2A2D36);
    final menuBg = dark ? const Color(0xFF1E2128) : const Color(0xFF2F333C);
    final fg = const Color(0xFFD7DAE0);

    return DropdownMenu<String>(
      key: ValueKey('cat_$current'),
      initialSelection: current,
      requestFocusOnTap: false,
      enableFilter: false,
      enableSearch: false,
      expandedInsets: EdgeInsets.zero,
      menuHeight: 280,
      hintText: hint,
      textStyle: TextStyle(
        color: fg,
        fontSize: 14,
        fontWeight: FontWeight.w500,
      ),
      inputDecorationTheme: InputDecorationTheme(
        isDense: true,
        filled: true,
        fillColor: bg,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF5B6478), width: 1),
        ),
      ),
      menuStyle: MenuStyle(
        backgroundColor: WidgetStatePropertyAll(menuBg),
        shape: WidgetStatePropertyAll(
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        elevation: const WidgetStatePropertyAll(8),
        side: WidgetStatePropertyAll(
          BorderSide(
            color: const Color(0xFF3A3F4B).withValues(alpha: 0.6),
            width: 0.5,
          ),
        ),
      ),
      trailingIcon: Icon(Icons.keyboard_arrow_down_rounded, color: fg),
      onSelected: (v) => onChanged(v == _all ? null : v),
      dropdownMenuEntries: [
        if (includeAll)
          const DropdownMenuEntry<String>(value: _all, label: '全部分类'),
        for (final c in categories)
          DropdownMenuEntry<String>(value: c, label: c),
      ],
    );
  }
}
