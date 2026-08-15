import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';

class BootstrapState {
  const BootstrapState({
    this.isLoading = true,
    this.required = false,
    this.provider = 'deepseek',
    this.baseUrl = '',
    this.keyTail = '',
    this.message = '',
    this.isError = false,
  });

  final bool isLoading;
  final bool required;
  final String provider;
  final String baseUrl;
  final String keyTail;
  final String message;
  final bool isError;

  BootstrapState copyWith({
    bool? isLoading,
    bool? required,
    String? provider,
    String? baseUrl,
    String? keyTail,
    String? message,
    bool? isError,
  }) {
    return BootstrapState(
      isLoading: isLoading ?? this.isLoading,
      required: required ?? this.required,
      provider: provider ?? this.provider,
      baseUrl: baseUrl ?? this.baseUrl,
      keyTail: keyTail ?? this.keyTail,
      message: message ?? this.message,
      isError: isError ?? this.isError,
    );
  }
}

class BootstrapController extends Notifier<BootstrapState> {
  @override
  BootstrapState build() => const BootstrapState();

  void showMessage(String message, {bool isError = false}) {
    state = state.copyWith(message: message, isError: isError);
  }

  Future<void> load() async {
    state = state.copyWith(isLoading: true, message: '', isError: false);
    try {
      final status = await ref.read(apiClientProvider).getBootstrapStatus();
      state = BootstrapState(
        isLoading: false,
        required: status.required,
        provider: status.provider,
        baseUrl: status.baseUrl,
        keyTail: status.keyTail,
        message: status.required ? '请配置 API Key 后开始使用' : '',
      );
    } catch (e) {
      state = BootstrapState(
        isLoading: false,
        required: true,
        provider: 'deepseek',
        baseUrl: '',
        message: '无法连接本地服务: ${_errorText(e)}',
        isError: true,
      );
    }
  }

  Future<bool> test({
    required String provider,
    required String apiKey,
    required String baseUrl,
  }) async {
    state = state.copyWith(message: '正在验证 Key ...', isError: false);
    try {
      final result = await ref.read(apiClientProvider).testBootstrap(
            provider: provider,
            apiKey: apiKey,
            baseUrl: baseUrl,
          );
      state = state.copyWith(
        message: result.ok
            ? '连接成功: ${result.keyTail}'
            : '${result.message}${result.errorCode == null ? '' : ' (${result.errorCode})'}',
        isError: !result.ok,
        keyTail: result.keyTail,
      );
      return result.ok;
    } catch (e) {
      state = state.copyWith(message: '验证失败: ${_errorText(e)}', isError: true);
      return false;
    }
  }

  Future<bool> configure({
    required String provider,
    required String apiKey,
    required String baseUrl,
  }) async {
    state = state.copyWith(message: '正在验证并保存 ...', isError: false);
    try {
      final result = await ref.read(apiClientProvider).configureBootstrap(
            provider: provider,
            apiKey: apiKey,
            baseUrl: baseUrl,
          );
      if (result.ok) {
        state = BootstrapState(
          isLoading: false,
          required: false,
          provider: result.provider.isEmpty ? provider : result.provider,
          baseUrl: baseUrl,
          keyTail: result.keyTail,
          message: '配置成功，正在进入 ...',
        );
        return true;
      }
      state = state.copyWith(
        message:
            '${result.message}${result.errorCode == null ? '' : ' (${result.errorCode})'}',
        isError: true,
        keyTail: result.keyTail,
      );
      return false;
    } catch (e) {
      state = state.copyWith(message: '保存失败: ${_errorText(e)}', isError: true);
      return false;
    }
  }

  String _errorText(Object e) {
    if (e is ApiException) {
      return e.display;
    }
    if (e is DioException) {
      final data = e.response?.data;
      if (data is Map && data['detail'] != null) {
        return data['detail'].toString();
      }
      if (data is Map && data['message'] != null) {
        return data['message'].toString();
      }
      return e.message ?? e.type.name;
    }
    return e.toString();
  }
}

final bootstrapControllerProvider =
    NotifierProvider<BootstrapController, BootstrapState>(
  BootstrapController.new,
);
