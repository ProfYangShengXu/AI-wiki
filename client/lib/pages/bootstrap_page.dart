import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/bootstrap_controller.dart';

/// 首次进入灰屏：强制配置 API Key，无关闭/跳过入口。
class BootstrapPage extends ConsumerStatefulWidget {
  const BootstrapPage({super.key});

  @override
  ConsumerState<BootstrapPage> createState() => _BootstrapPageState();
}

class _BootstrapPageState extends ConsumerState<BootstrapPage> {
  final _keyController = TextEditingController();
  final _baseUrlController = TextEditingController();
  String _provider = 'deepseek';
  String _model = 'deepseek-v4-flash';
  bool _obscureKey = true;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final state = ref.read(bootstrapControllerProvider);
    _provider = state.provider;
    _baseUrlController.text = state.baseUrl;
  }

  @override
  void dispose() {
    _keyController.dispose();
    _baseUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(bootstrapControllerProvider);
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: const Color(0xFF111827),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF1E293B), Color(0xFF0F172A)],
          ),
        ),
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Card(
                elevation: 12,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 26, 24, 20),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '🍌 StudyWiki-Agent',
                        style: theme.textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '首次配置',
                        style: theme.textTheme.bodyMedium
                            ?.copyWith(color: theme.colorScheme.outline),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        '配置大模型 API Key 后才能开始使用。主界面已被锁定，此步骤不可跳过。',
                        style: theme.textTheme.bodySmall
                            ?.copyWith(height: 1.5),
                      ),
                      const SizedBox(height: 16),
                      _label('Provider'),
                      // 受控下拉: value 每次 build 同步 _provider
                      DropdownButton<String>(
                        value: _provider,
                        isExpanded: true,
                        underline: const SizedBox.shrink(),
                        items: const [
                          DropdownMenuItem(
                            value: 'deepseek',
                            child: Text('DeepSeek'),
                          ),
                          DropdownMenuItem(
                            value: 'openai',
                            child: Text('OpenAI'),
                          ),
                          DropdownMenuItem(
                            value: 'kimi',
                            child: Text('Kimi (月之暗面)'),
                          ),
                          DropdownMenuItem(
                            value: 'glm',
                            child: Text('GLM (智谱)'),
                          ),
                          DropdownMenuItem(
                            value: 'grok',
                            child: Text('Grok (xAI)'),
                          ),
                          DropdownMenuItem(
                            value: 'anthropic',
                            child: Text('Claude (Anthropic)'),
                          ),
                          DropdownMenuItem(
                            value: 'gemini',
                            child: Text('Gemini (Google)'),
                          ),
                        ],
                        onChanged: _busy
                            ? null
                            : (value) {
                                if (value == null) return;
                                setState(() {
                                  _provider = value;
                                  final defaults = _providerDefaults(value);
                                  _model = defaults.$1;
                                  if (_baseUrlController.text.isEmpty) {
                                    _baseUrlController.text = defaults.$2;
                                  }
                                });
                              },
                      ),
                      const SizedBox(height: 12),
                      _label('API Key'),
                      TextField(
                        controller: _keyController,
                        enabled: !_busy,
                        obscureText: _obscureKey,
                        autofillHints: const [AutofillHints.password],
                        decoration: InputDecoration(
                          hintText: 'sk-...',
                          suffixIcon: IconButton(
                            onPressed: _busy
                                ? null
                                : () => setState(
                                    () => _obscureKey = !_obscureKey),
                            icon: Icon(
                              _obscureKey
                                  ? Icons.visibility
                                  : Icons.visibility_off,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      _label('模型 (Model)'),
                      // 受控模型下拉: 选项随 provider 变化
                      DropdownButton<String>(
                        value: _model,
                        isExpanded: true,
                        underline: const SizedBox.shrink(),
                        items: _modelOptions(_provider)
                            .map(
                              (m) => DropdownMenuItem(value: m, child: Text(m)),
                            )
                            .toList(),
                        onChanged: _busy
                            ? null
                            : (value) {
                                if (value != null) {
                                  setState(() => _model = value);
                                }
                              },
                      ),
                      const SizedBox(height: 12),
                      _label('API Base URL'),
                      TextField(
                        controller: _baseUrlController,
                        enabled: !_busy,
                        decoration: const InputDecoration(
                          hintText: 'https://api.deepseek.com',
                        ),
                      ),
                      const SizedBox(height: 20),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: _busy ? null : _test,
                              child: const Text('测试连接'),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: FilledButton(
                              onPressed: _busy ? null : _save,
                              child: const Text('保存并进入'),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 200),
                        child: Text(
                          state.message,
                          key: ValueKey(state.message),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: state.isError
                                ? theme.colorScheme.error
                                : state.message.startsWith('连接成功') ||
                                        state.message.startsWith('配置成功')
                                    ? Colors.green
                                    : theme.colorScheme.outline,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// 各厂商默认 (model, base_url) — 与后端 config/bootstrap 保持一致。
  (String, String) _providerDefaults(String provider) {
    switch (provider) {
      case 'openai':
        return ('gpt-4o-mini', 'https://api.openai.com/v1');
      case 'kimi':
        return ('moonshot-v1-8k', 'https://api.moonshot.cn/v1');
      case 'glm':
        return ('glm-4-flash', 'https://open.bigmodel.cn/api/paas/v4');
      case 'grok':
        return ('grok-3-mini', 'https://api.x.ai/v1');
      case 'anthropic':
        return ('claude-sonnet-4-5', 'https://api.anthropic.com');
      case 'gemini':
        return ('gemini-2.0-flash', '');
      default:
        return ('deepseek-v4-flash', 'https://api.deepseek.com');
    }
  }

  /// 各厂商可选模型列表(供下拉选择)。
  List<String> _modelOptions(String provider) {
    switch (provider) {
      case 'openai':
        return const ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo'];
      case 'kimi':
        return const ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'];
      case 'glm':
        return const ['glm-4-flash', 'glm-4', 'glm-4-plus'];
      case 'grok':
        return const ['grok-3-mini', 'grok-3', 'grok-2'];
      case 'anthropic':
        return const ['claude-sonnet-4-5', 'claude-opus-4-5', 'claude-3-5-haiku'];
      case 'gemini':
        return const ['gemini-2.0-flash', 'gemini-2.5-pro', 'gemini-1.5-pro'];
      default:
        return const ['deepseek-v4-flash', 'deepseek-v4-pro'];
    }
  }

  Widget _label(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(
        text,
        style: Theme.of(context)
            .textTheme
            .labelMedium
            ?.copyWith(fontWeight: FontWeight.w700),
      ),
    );
  }

  Future<void> _test() async {
    final key = _keyController.text.trim();
    if (key.isEmpty) {
      setState(() {});
      ref
          .read(bootstrapControllerProvider.notifier)
          .showMessage('请先填写 API Key', isError: true);
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(bootstrapControllerProvider.notifier).test(
            provider: _provider,
            apiKey: key,
            baseUrl: _baseUrlController.text.trim(),
            model: _model,
          );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final key = _keyController.text.trim();
    if (key.isEmpty) {
      ref
          .read(bootstrapControllerProvider.notifier)
          .showMessage('请先填写 API Key', isError: true);
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(bootstrapControllerProvider.notifier).configure(
            provider: _provider,
            apiKey: key,
            baseUrl: _baseUrlController.text.trim(),
            model: _model,
          );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}
