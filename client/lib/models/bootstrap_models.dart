class BootstrapStatus {
  const BootstrapStatus({
    required this.required,
    required this.provider,
    required this.hasKey,
    required this.keyTail,
    required this.baseUrl,
  });

  final bool required;
  final String provider;
  final bool hasKey;
  final String keyTail;
  final String baseUrl;

  factory BootstrapStatus.fromJson(Map<String, dynamic> json) {
    return BootstrapStatus(
      required: json['required'] == true,
      provider: json['provider'] as String? ?? 'deepseek',
      hasKey: json['has_key'] == true,
      keyTail: json['key_tail'] as String? ?? '',
      baseUrl: json['base_url'] as String? ?? '',
    );
  }
}

class BootstrapActionResult {
  const BootstrapActionResult({
    required this.ok,
    required this.message,
    required this.keyTail,
    this.provider = '',
    this.errorCode,
  });

  final bool ok;
  final String message;
  final String keyTail;
  final String provider;
  final String? errorCode;

  factory BootstrapActionResult.fromJson(Map<String, dynamic> json) {
    return BootstrapActionResult(
      ok: json['ok'] == true,
      message: json['message'] as String? ?? '',
      keyTail: json['key_tail'] as String? ?? '',
      provider: json['provider'] as String? ?? '',
      errorCode: json['error_code'] as String?,
    );
  }
}
