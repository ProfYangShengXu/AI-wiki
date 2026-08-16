import 'dart:ffi';

import 'package:ffi/ffi.dart';

// ── user32.dll 函数类型定义(必须位于顶层) ──────────────
typedef _FindWindowWNative = IntPtr Function(
    Pointer<Utf16> lpClassName, Pointer<Utf16> lpWindowName);
typedef _FindWindowWDart = int Function(
    Pointer<Utf16> lpClassName, Pointer<Utf16> lpWindowName);

typedef _ShowWindowNative = Int32 Function(IntPtr hWnd, Int32 nCmdShow);
typedef _ShowWindowDart = int Function(int hWnd, int nCmdShow);

typedef _SetForegroundWindowNative = Int32 Function(IntPtr hWnd);
typedef _SetForegroundWindowDart = int Function(int hWnd);

typedef _SetWindowPosNative = Int32 Function(
    IntPtr hWnd, IntPtr hWndInsertAfter, Int32 x, Int32 y,
    Int32 cx, Int32 cy, Uint32 uFlags);
typedef _SetWindowPosDart = int Function(
    int hWnd, int hWndInsertAfter, int x, int y, int cx, int cy, int uFlags);

typedef _IsWindowVisibleNative = Int32 Function(IntPtr hWnd);
typedef _IsWindowVisibleDart = int Function(int hWnd);

/// 纯 Win32 窗口控制(替代 window_manager 插件,避免原生调用挂死)。
///
/// 直接经 user32.dll 操作标题为 "StudyWiki-Agent" 的窗口:
/// - [ensureVisible]: 显示 + 置前 + 移到屏幕可见区域(隐藏/屏幕外兜底);
/// - [show] / [hide]: 托盘场景的显示/隐藏。
///
/// 所有调用为同步 Win32 API,不依赖消息循环,异常全部吞掉。
class Win32Window {
  Win32Window._();

  static const String windowTitle = 'StudyWiki-Agent';

  static final DynamicLibrary _user32 = DynamicLibrary.open('user32.dll');

  static final _findWindowW =
      _user32.lookupFunction<_FindWindowWNative, _FindWindowWDart>('FindWindowW');
  static final _showWindow =
      _user32.lookupFunction<_ShowWindowNative, _ShowWindowDart>('ShowWindow');
  static final _setForeground = _user32.lookupFunction<
      _SetForegroundWindowNative, _SetForegroundWindowDart>(
      'SetForegroundWindow');
  static final _setWindowPos = _user32.lookupFunction<
      _SetWindowPosNative, _SetWindowPosDart>('SetWindowPos');
  static final _isWindowVisible = _user32.lookupFunction<
      _IsWindowVisibleNative, _IsWindowVisibleDart>('IsWindowVisible');

  static const int swHide = 0;
  static const int swShowNormal = 1;
  static const int swRestore = 9;
  static const int hwndTop = 0;
  static const int swpShowWindow = 0x0040;
  static const int swpNoZOrder = 0x0004;

  static int? _find() {
    final title = windowTitle.toNativeUtf16();
    try {
      final hwnd = _findWindowW(nullptr, title);
      return hwnd == 0 ? null : hwnd;
    } catch (_) {
      return null;
    } finally {
      malloc.free(title);
    }
  }

  static bool show() {
    try {
      final hwnd = _find();
      if (hwnd == null) return false;
      _showWindow(hwnd, swShowNormal);
      _showWindow(hwnd, swRestore);
      _setForeground(hwnd);
      return true;
    } catch (_) {
      return false;
    }
  }

  static bool hide() {
    try {
      final hwnd = _find();
      if (hwnd == null) return false;
      _showWindow(hwnd, swHide);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// 兜底:显示 + 置前 + 把窗口移到屏幕可见坐标(防"窗口在屏幕外")。
  static bool ensureVisible() {
    try {
      final hwnd = _find();
      if (hwnd == null) return false;
      _showWindow(hwnd, swShowNormal);
      // 移到 (80, 60), 1280x800,并强制显示
      _setWindowPos(
          hwnd, hwndTop, 80, 60, 1280, 800, swpShowWindow | swpNoZOrder);
      _setForeground(hwnd);
      return true;
    } catch (_) {
      return false;
    }
  }

  static bool isVisible() {
    try {
      final hwnd = _find();
      if (hwnd == null) return false;
      return _isWindowVisible(hwnd) != 0;
    } catch (_) {
      return false;
    }
  }
}
