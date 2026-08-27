import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/api_client.dart';
import '../core/api_config.dart';
import '../models/pair_models.dart';
import '../services/server_config.dart';
import '../state/bootstrap_controller.dart';
import '../widgets/app_snackbar.dart';
import 'qr_scan_page.dart';

/// 配对页：6 位配对码输入 + 配对二维码生成 + 服务器地址配置。
///
/// - 输入配对码 → `POST /api/pair/verify {code, device_id}`（后端端点待补）。
/// - 生成二维码 → 内容为 [PairPayload] 单行 JSON，供其它设备扫码配对。
class PairingPage extends ConsumerStatefulWidget {
  const PairingPage({super.key});

  @override
  ConsumerState<PairingPage> createState() => _PairingPageState();
}

class _PairingPageState extends ConsumerState<PairingPage> {
  static const _deviceIdKey = 'pair_device_id';

  final _codeController = TextEditingController();
  final _serverController = TextEditingController();

  String _deviceId = '';
  String _qrPayload = '';
  bool _busy = false;
  String _resultMessage = '';
  bool _resultError = false;

  @override
  void initState() {
    super.initState();
    _serverController.text = ApiConfig.baseUrl;
    _loadDeviceId();
  }

  @override
  void dispose() {
    _codeController.dispose();
    _serverController.dispose();
    super.dispose();
  }

  Future<void> _loadDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(_deviceIdKey);
    final id = (stored == null || stored.isEmpty) ? generateDeviceId() : stored;
    if (stored == null || stored.isEmpty) {
      await prefs.setString(_deviceIdKey, id);
    }
    if (!mounted) return;
    setState(() {
      _deviceId = id;
      _qrPayload = PairPayload(
        code: PairCode.generate(),
        server: _serverController.text.trim(),
        deviceId: id,
      ).encode();
    });
  }

  void _regenerateQr() {
    if (_deviceId.isEmpty) return;
    setState(() {
      _qrPayload = PairPayload(
        code: PairCode.generate(),
        server: _serverController.text.trim(),
        deviceId: _deviceId,
      ).encode();
    });
  }

  /// 扫码配对: 扫描电脑端二维码 → 解析出 server + code → 自动验证。
  Future<void> _scanQr() async {
    final raw = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => const QrScanPage()),
    );
    if (raw == null || !mounted) return;
    final payload = PairPayload.decode(raw);
    if (payload == null) {
      if (mounted) AppSnack.error(context, '无法识别的二维码, 请扫描配对二维码');
      return;
    }
    setState(() {
      _serverController.text = payload.server;
      _codeController.text = payload.code;
    });
    await _verify();
  }

  Future<void> _verify() async {
    final code = PairCode.normalize(_codeController.text);
    if (!PairCode.isValid(code)) {
      setState(() {
        _resultMessage = '请输入 6 位数字配对码';
        _resultError = true;
      });
      return;
    }
    final server = _serverController.text.trim();
    if (server.isEmpty) {
      setState(() {
        _resultMessage = '请填写服务器地址';
        _resultError = true;
      });
      return;
    }
    setState(() {
      _busy = true;
      _resultMessage = '正在配对...';
      _resultError = false;
    });
    try {
      final result = await ref.read(pairApiProvider).verify(
            baseUrl: server,
            code: code,
            deviceId: _deviceId,
          );
      if (!mounted) return;
      setState(() {
        _resultMessage = result.message;
        _resultError = !result.ok;
      });
      if (result.ok) {
        // 持久化服务器地址 + 通知全局 ApiClient 切换 baseUrl
        await ServerConfig.save(server);
        ref.read(serverBaseUrlProvider.notifier).state = server;
        // 重新检查 bootstrap(后端已可达则直接进入主界面)
        ref.read(bootstrapControllerProvider.notifier).load();
        if (mounted) {
          AppSnack.info(context, '配对成功, 已连接 $server');
          Navigator.of(context).pop();
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _resultMessage = '配对失败: $e';
        _resultError = true;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('设备配对')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _sectionTitle(theme, '服务器地址'),
              TextField(
                controller: _serverController,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  hintText: 'http://192.168.1.10:8000',
                  border: OutlineInputBorder(),
                ),
                onChanged: (_) => _regenerateQr(),
              ),
              const SizedBox(height: 16),
              _sectionTitle(theme, '输入配对码（作为新设备）'),
              TextField(
                controller: _codeController,
                keyboardType: TextInputType.number,
                maxLength: 8,
                decoration: const InputDecoration(
                  hintText: '6 位数字，如 123456',
                  border: OutlineInputBorder(),
                  counterText: '',
                ),
              ),
              const SizedBox(height: 8),
              if (Platform.isAndroid || Platform.isIOS)
                OutlinedButton.icon(
                  onPressed: _busy ? null : _scanQr,
                  icon: const Icon(Icons.qr_code_scanner),
                  label: const Text('扫码配对(推荐)'),
                ),
              const SizedBox(height: 8),
              FilledButton.icon(
                onPressed: _busy ? null : _verify,
                icon: _busy
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.link),
                label: const Text('验证配对'),
              ),
              if (_resultMessage.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  _resultMessage,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: _resultError
                        ? theme.colorScheme.error
                        : Colors.green,
                  ),
                ),
              ],
              const SizedBox(height: 16),
              _sectionTitle(theme, '生成配对二维码（作为主设备）'),
              Center(
                child: _qrPayload.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.all(24),
                        child: CircularProgressIndicator(),
                      )
                    : Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: theme.colorScheme.outlineVariant),
                        ),
                        child: QrImageView(
                          data: _qrPayload,
                          version: QrVersions.auto,
                          size: 200,
                          backgroundColor: Colors.white,
                        ),
                      ),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _deviceId.isEmpty ? null : _regenerateQr,
                icon: const Icon(Icons.refresh),
                label: const Text('重新生成'),
              ),
              const SizedBox(height: 16),
              _sectionTitle(theme, '本机设备标识'),
              Text(
                _deviceId.isEmpty ? '加载中...' : _deviceId,
                style: theme.textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionTitle(ThemeData theme, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(
        text,
        style: theme.textTheme.labelLarge
            ?.copyWith(fontWeight: FontWeight.w700),
      ),
    );
  }
}
