# 培训管理系统 Android APK

该壳应用只访问 `https://8.148.25.74/`，禁止明文 HTTP，并只信任项目服务器私有 CA。用户安装 APK 后无需额外安装证书。

APK 由 GitHub Actions 构建：进入仓库的 **Actions → Build Android APK**，选择一次工作流运行后，在该运行页的 **Artifacts** 下载 APK。

## 首次配置正式签名（只需一次）

为确保以后的 APK 可以直接覆盖更新，请在 GitHub 仓库 **Settings → Secrets and variables → Actions** 配置以下四个 Secrets：

- `ANDROID_KEYSTORE_BASE64`：正式 `.p12` 或 `.jks` 签名文件的 Base64 文本
- `ANDROID_KEYSTORE_PASSWORD`：签名文件密码
- `ANDROID_KEY_ALIAS`：密钥别名
- `ANDROID_KEY_PASSWORD`：别名密码

没有配置这些 Secrets 时，工作流仍会产出可安装的测试 APK，但每次构建的签名不同，不能用于后续覆盖更新。正式使用前务必配置上述 Secrets；签名私钥不要提交到 Git 或发送给他人。
