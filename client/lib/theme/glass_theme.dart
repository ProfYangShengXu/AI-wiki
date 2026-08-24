import 'dart:ui';

import 'package:flutter/material.dart';

/// iOS / Vision Pro 风格主题 — 毛玻璃 + 渐变 + 极简层级。
///
/// 用法:
/// - MaterialApp.theme / darkTheme 用 [buildTheme]
/// - 毛玻璃卡片用 [glassCard] 包装 (BackdropFilter + 半透明 + 细描边)
/// - 渐变背景用 [gradientBackground] 包住 Scaffold body
class GlassTheme {
  GlassTheme._();

  // ── 主色: 蓝紫渐变 (iOS 风格) ──────────────────────
  static const Color primary = Color(0xFF3B82F6);
  static const Color accent = Color(0xFF8B5CF6);

  static LinearGradient get backgroundGradient => const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Color(0xFFEFF6FF),
          Color(0xFFF5F3FF),
          Color(0xFFFDF2F8),
        ],
      );

  static LinearGradient get darkBackgroundGradient => const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Color(0xFF0B1220),
          Color(0xFF111827),
          Color(0xFF1E1B2E),
        ],
      );

  /// 毛玻璃卡片包装: BackdropFilter 模糊 + 半透明填充 + 0.5px 细描边。
  static Widget glassCard({
    required Widget child,
    EdgeInsetsGeometry padding = const EdgeInsets.all(16),
    BorderRadius radius = const BorderRadius.all(Radius.circular(20)),
    double blur = 24,
    double opacity = 0.55,
    Color? borderColor,
  }) {
    return ClipRRect(
      borderRadius: radius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: opacity),
            borderRadius: radius,
            border: Border.all(
              color: borderColor ?? Colors.white.withValues(alpha: 0.5),
              width: 0.5,
            ),
          ),
          child: child,
        ),
      ),
    );
  }

  /// 页面渐变背景 (配合 Scaffold 使用)。
  ///
  /// 模拟 iOS 壁纸: 线性渐变打底 + 从中心/角落散开的径向辉光光斑。
  static Widget background(BuildContext context, {required Widget child}) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: dark ? darkBackgroundGradient : backgroundGradient,
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          // 径向辉光光斑 (大范围径向模糊感)
          Positioned(
            top: -120,
            right: -80,
            child: _glowOrb(
              dark
                  ? const Color(0x333B82F6)
                  : const Color(0x553B82F6),
              size: 420,
            ),
          ),
          Positioned(
            bottom: -140,
            left: -60,
            child: _glowOrb(
              dark
                  ? const Color(0x228B5CF6)
                  : const Color(0x448B5CF6),
              size: 380,
            ),
          ),
          Positioned(
            top: 240,
            left: -120,
            child: _glowOrb(
              dark
                  ? const Color(0x1FEC4899)
                  : const Color(0x33EC4899),
              size: 300,
            ),
          ),
          child,
        ],
      ),
    );
  }

  static Widget _glowOrb(Color color, {required double size}) {
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, color.withValues(alpha: 0)],
          ),
        ),
      ),
    );
  }

  static ThemeData buildTheme({required Brightness brightness}) {
    final dark = brightness == Brightness.dark;
    final scheme = ColorScheme.fromSeed(
      seedColor: primary,
      brightness: brightness,
      dynamicSchemeVariant: DynamicSchemeVariant.fidelity,
    ).copyWith(
      primary: primary,
      secondary: accent,
      surface: dark ? const Color(0xFF1A2233) : const Color(0xFFF8FAFF),
    );
    final baseText = dark ? const Color(0xFFE5E7EB) : const Color(0xFF1F2937);

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: Colors.transparent,
      fontFamily: null, // 系统字体 (Windows 默认 Segoe UI, 视觉接近 SF Pro)
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        foregroundColor: baseText,
        titleTextStyle: TextStyle(
          color: baseText,
          fontSize: 22,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.3,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: Colors.white.withValues(alpha: dark ? 0.08 : 0.55),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(
            color: Colors.white.withValues(alpha: dark ? 0.1 : 0.5),
            width: 0.5,
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white.withValues(alpha: dark ? 0.06 : 0.6),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(
            color: Colors.white.withValues(alpha: 0.5),
            width: 0.5,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: primary, width: 1.5),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: Colors.white.withValues(alpha: dark ? 0.1 : 0.7),
        indicatorColor: primary.withValues(alpha: 0.15),
        surfaceTintColor: Colors.transparent,
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: Colors.transparent,
        indicatorColor: primary.withValues(alpha: 0.15),
      ),
      listTileTheme: ListTileThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: Colors.white.withValues(alpha: dark ? 0.08 : 0.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        side: BorderSide(
          color: Colors.white.withValues(alpha: 0.5),
          width: 0.5,
        ),
      ),
      dividerTheme: DividerThemeData(
        color: Colors.white.withValues(alpha: dark ? 0.08 : 0.3),
        thickness: 0.5,
        space: 1,
      ),
      textTheme: TextTheme(
        headlineSmall: TextStyle(
          color: baseText,
          fontSize: 26,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.5,
        ),
        titleMedium: TextStyle(
          color: baseText,
          fontSize: 17,
          fontWeight: FontWeight.w600,
        ),
        bodyMedium: TextStyle(
          color: baseText,
          fontSize: 14,
          fontWeight: FontWeight.w400,
          height: 1.5,
        ),
        bodySmall: TextStyle(
          color: baseText.withValues(alpha: 0.6),
          fontSize: 12,
          fontWeight: FontWeight.w300,
        ),
      ),
      splashFactory: InkRipple.splashFactory,
    );
  }
}

/// 弹性回弹按压容器 — iOS 上下文菜单式反馈。
///
/// 按下时缩小到 [pressedScale] (默认 0.96), 松手用弹性曲线回弹。
class SpringPress extends StatefulWidget {
  const SpringPress({
    super.key,
    required this.child,
    this.onTap,
    this.pressedScale = 0.96,
    this.duration = const Duration(milliseconds: 260),
  });

  final Widget child;
  final VoidCallback? onTap;
  final double pressedScale;
  final Duration duration;

  @override
  State<SpringPress> createState() => _SpringPressState();
}

class _SpringPressState extends State<SpringPress> {
  bool _pressed = false;

  void _setPressed(bool value) {
    if (_pressed != value) setState(() => _pressed = value);
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) => _setPressed(true),
      onTapUp: (_) => _setPressed(false),
      onTapCancel: () => _setPressed(false),
      onTap: widget.onTap,
      child: AnimatedScale(
        scale: _pressed ? widget.pressedScale : 1.0,
        duration: widget.duration,
        curve: _pressed
            ? Curves.easeOut
            : Curves.easeOutBack,
        child: widget.child,
      ),
    );
  }
}

/// 页面切换过渡 — 平滑缩放 + 淡入 (iOS transition 手势感)。
class GlassPageTransition extends StatelessWidget {
  const GlassPageTransition({
    super.key,
    required this.child,
    this.duration = const Duration(milliseconds: 320),
  });

  final Widget child;
  final Duration duration;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.94, end: 1.0),
      duration: duration,
      curve: Curves.easeOutCubic,
      builder: (context, value, child) => Opacity(
        opacity: 0.6 + 0.4 * value,
        child: Transform.scale(scale: value, child: child),
      ),
      child: child,
    );
  }
}
