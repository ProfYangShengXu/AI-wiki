# StudyWiki-Agent Flutter 客户端

Android / Windows 共享 Flutter 前端。首次进入时调用后端 `/api/bootstrap/status`，未配置 API Key 会显示不可跳过的灰屏配置页。

## 目录

```text
lib/
├── main.dart                         # 入口
├── app.dart                          # MaterialApp + BootstrapGate
├── core/
│   ├── api_config.dart               # Android/Windows 默认服务地址
│   └── api_client.dart               # Dio 封装 REST 与 WebSocket URI
├── models/
│   ├── bootstrap_models.dart         # 灰屏状态模型
│   └── knowledge_card.dart           # 知识卡片模型
├── state/
│   └── bootstrap_controller.dart     # Riverpod 灰屏状态控制器
└── pages/
    ├── bootstrap_page.dart           # 首次进入灰屏强制配置 API Key
    ├── home_shell.dart               # 桌面/手机自适应导航壳
    ├── wiki_page.dart                # 分类、卡片列表与详情
    ├── chat_page.dart                # Ask/Agent WebSocket 对话
    ├── quiz_page.dart                # Quiz 生成与评分
    └── settings_page.dart            # 服务地址与配置状态
```

## 首次运行

先启动后端：

```bat
cd /d C:\Users\45140\OneDrive\Desktop\code\AIwiki2.0
start_studywiki.bat
```

再生成平台壳并运行（本仓库只提交了 Dart 源码，平台目录由 flutter create 生成）：

```bash
cd client
flutter create . --platforms=android,windows --org com.studywiki --project-name studywiki_client
flutter pub get

# Windows
flutter run -d windows

# Android（模拟器默认通过 10.0.2.2 访问宿主机）
flutter run -d android
```

自定义后端地址：

```bash
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000
```

## 灰屏规则

- 后端返回 `required=true` 时只显示灰屏，不初始化主界面。
- 灰屏没有关闭/跳过入口。
- “测试连接”只验证不保存。
- “保存并进入”验证成功后写入后端 `.env` 并进入主界面。
