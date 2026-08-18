import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 数据刷新信号:导入完成等写操作后自增,监听方(如知识库列表)据此重新加载。
final dataRefreshProvider = StateProvider<int>((ref) => 0);
