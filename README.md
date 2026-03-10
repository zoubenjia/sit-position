[🇬🇧 English](#sit-position--posture-monitor--exercise-coach) | [🇨🇳 中文](#sit-position--坐姿监控--运动教练)

# Sit Position — Posture Monitor & Exercise Coach

Real-time sitting/standing posture detection via camera, voice-guided push-up training. Supports macOS and Windows 10/11. Bilingual Chinese/English support.

<p align="center">
  <img src="docs/demo_en.gif" alt="Sit Monitor Demo" width="600">
</p>

## Features

### Sitting/Standing Posture Monitoring
- **Posture Detection** — Four metrics: shoulder tilt, head forward, head tilt, torso lean. Works for both sitting and standing.
- **Dynamic Icons** — Tray icon reflects specific posture issues in real time: neck forward / head tilt / uneven shoulders / torso lean, each with distinct shape and color.
- **Standing Desk Support** — Three modes: Auto-detect / Sitting / Standing, switchable from the tray menu.
- **Pop-up Alerts** — Auto alert on sustained bad posture, with adjustable thresholds and duration.
- **Positive Feedback** — Voice encouragement after posture correction; milestone celebration at 15/30/60/120 minutes of sustained good posture
- **Sedentary/Standing Reminders** — Alert after 45 minutes of continuous sitting or standing (adjustable).
- **Auto-Pause on Leave** — Auto-pauses browser video when you leave the camera, resumes on return (Chrome/Safari/Arc/Firefox).
- **Meeting Compatible** — Yields camera during video calls, reconnects after.
- **Auto-Start** — One command to install as a background service.

### Push-up Training
- **Voice-Guided Setup** — Step-by-step: place laptop → stand → lie down → ready
- **Real-time Counting** — Voice counts "one, two, three..."
- **Form Correction** — Hip sag/pike, shallow depth, head drop
- **Auto-Finish** — Stand up to end training, summary announced
- **Training Log** — Data saved to `logs/exercise.jsonl`, queryable via MCP

### Push-up Battles
- **Quick Battle** — One-click opponent selection from leaderboard for push-up PK
- **Quality-Weighted Scoring** — `score = reps × (0.7 + 0.3 × good_reps / reps)`, encourages quality without penalizing quantity
- **Async Mode** — Each player completes independently, winner determined automatically
- **Rep Grading** — Each rep auto-graded as good / shallow / bad, factored into battle score
- **Battle Achievements** — First battle, winner, 3-win streak

### Leaderboard & Social (Cloud, Optional)
- **Daily/Weekly Leaderboard** — Ranked by good posture rate
- **Achievement System** — 13 badges including Focus 30/60/120 (sustained good posture), streaks, battle wins, and more
- **Likes** — Give likes to other users' daily reports
- **Friend Challenges** — Challenge others on posture rate / monitoring duration
- **Google Login** — Optional Google account linking for multi-device sync, unlinkable anytime
- **Privacy Control** — Off by default; data sharing toggleable anytime
- **Zero Barrier** — No account required, device auto-binds identity, just set a nickname

### Multilingual Support (i18n)
- **Chinese/English Bilingual** — Menu, notifications, voice, reports fully localized
- **One-Click Switch** — Toggle at the bottom of tray menu: 🌐 English / 🌐 中文
- **TTS Auto-Adaptation** — Chinese uses Tingting, English uses Samantha (macOS)
- **Easy to Extend** — Pure Python dict implementation, add a new language by creating one `.py` file

### Simple / Advanced Mode
- **Simple Mode** (default) — Shows only monitoring, training, battles, stats. Clean for new users.
- **Advanced Mode** — Full settings, social, account management. Toggle at menu bottom.

## System Requirements

### macOS
- macOS 13+ (Ventura or later)
- MacBook built-in camera or external camera
- tmux (for background running: `brew install tmux`)

### Windows
- Windows 10/11
- Camera (built-in or external)
- Python 3.12+ (check "Add Python to PATH" during install)

### Permissions

#### macOS Permissions

**1. Camera Permission (Required)**

Your terminal app (iTerm2 / Terminal) needs camera access:

> System Settings → Privacy & Security → Camera → Check your terminal app

If your terminal app isn't listed, the system will prompt on first run. If accidentally denied, manually enable it in the settings above.

**2. Accessibility Permission (for auto-pause)**

For `--auto-pause` video auto-pause, allow terminal to control other apps:

> System Settings → Privacy & Security → Accessibility → Check your terminal app

**3. Automation Permission (for auto-pause)**

On first video pause trigger, the system asks to allow terminal to control browsers. Select "Allow".

> If permissions don't take effect, try restarting the terminal app.

#### Windows Permissions

System prompts for camera permission on first run. Click "Allow".

> Settings → Privacy → Camera → Allow apps to access camera

## Installation

### Option 1: Download Binary (Easiest)

Download from [GitHub Releases](https://github.com/zoubenjia/sit-position/releases/latest):

- **macOS**: `SitMonitor-macOS.dmg` — Open and drag to Applications. Apple code-signed + notarized, Gatekeeper won't block.
- **Windows**: `SitMonitor-Windows.zip` — Extract and run `SitMonitor.exe`. No Python installation required.

### Option 2: Homebrew (Recommended, macOS)

```bash
brew tap zoubenjia/tap
brew install sit-monitor

# Start tray mode
sit-monitor --tray

# Auto-start on boot
brew services start sit-monitor
```

### Option 3: pip Install

```bash
pip install git+https://github.com/zoubenjia/sit-position.git

# Download model file manually
curl -sSL -o pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

### Option 4: From Source

**No Git?** Just [download ZIP](https://github.com/zoubenjia/sit-position/archive/refs/heads/main.zip), extract and run setup.

#### macOS

```bash
git clone https://github.com/zoubenjia/sit-position.git
cd sit-position
bash setup.sh    # One-click setup + auto-start + launch tray
```

#### Windows

```powershell
git clone https://github.com/zoubenjia/sit-position.git
cd sit-position
powershell -ExecutionPolicy Bypass -File setup.ps1    # One-click setup + auto-start + launch tray
```

> **PowerShell disabled?** Use the `.bat` alternative: `setup.bat`

## Background Service

### macOS

```bash
bash service.sh install   # Install auto-start
bash service.sh start     # Start
bash service.sh stop      # Stop
bash service.sh status    # Check status
bash service.sh update    # Update from remote
bash service.sh log       # View logs
```

### Windows (PowerShell)

```powershell
.\service.ps1 install     # Install auto-start + start
.\service.ps1 start       # Start
.\service.ps1 stop        # Stop
.\service.ps1 restart     # Restart
.\service.ps1 status      # Check status
.\service.ps1 update      # Update from remote
.\service.ps1 log         # View logs
.\service.ps1 uninstall   # Uninstall auto-start
```

### Windows (CMD — PowerShell disabled)

```cmd
service.bat install       & REM Install auto-start + start
service.bat start         & REM Start
service.bat stop          & REM Stop
service.bat restart       & REM Restart
service.bat status        & REM Check status
service.bat update        & REM Update from remote
service.bat log           & REM View logs
service.bat uninstall     & REM Uninstall auto-start
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--camera` | 0 | Camera index |
| `--interval` | 5.0 | Detection interval (seconds) |
| `--bad-seconds` | 30 | Bad posture duration before alert |
| `--cooldown` | 180 | Minimum interval between alerts |
| `--auto-pause` | off | Auto-pause video on leave |
| `--away-seconds` | 3.0 | Seconds away before pause |
| `--shoulder-threshold` | 10° | Shoulder tilt threshold |
| `--neck-threshold` | 15° | Head forward threshold |
| `--torso-threshold` | 8° | Torso lean threshold |
| `--debug` | off | Show camera feed and skeleton |

## Cloud Social (Optional)

Social features are off by default. To enable:

1. Click **"Enable Cloud"** in the tray menu
2. Set a nickname (Tray → Social → Nickname)
3. Leaderboard, achievements, and challenges become available

Cloud uses Supabase free tier. Data includes only posture stats (good rate, duration) — no images or personal info. Toggle **"Share Data"** to stop sharing anytime.

### MCP Tools

Available via AI assistants (Claude, etc.):

| Tool | Description |
|------|-------------|
| `social_leaderboard` | View daily/weekly leaderboard |
| `social_my_achievements` | View achievements |
| `social_send_like` | Like another user |
| `social_create_challenge` | Create a posture challenge |
| `social_my_challenges` | View challenges |
| `social_profile` | View social profile |
| `battle_create` | Create a push-up battle |
| `battle_accept` | Accept a battle invite |
| `battle_cancel` | Cancel a battle |
| `battle_list` | List my battles |
| `battle_details` | View battle details |
| `battle_start_exercise` | Start battle exercise |
| `auth_status` | Check auth status |
| `auth_link_google` | Link Google account |
| `auth_unlink_provider` | Unlink social account |

## Privacy

**Your privacy is the top priority.**

- All image processing is done **locally** — camera feed is **never saved or recorded**
- Only joint angle values are calculated — **no images stored**
- Cloud social is **off by default**; only posture stats (good rate, duration) are uploaded when enabled
- Data sharing can be turned off anytime
- No personal information collected
- Google login is optional, only fetches nickname and avatar, unlinkable anytime
- OAuth callback uses random port + state parameter for CSRF protection
- Fully open source for audit

## FAQ

**Q: "Camera in use" message after starting?**
A: Likely in a video call. The app waits for the camera to become available and auto-reconnects when the call ends.

**Q: Not receiving posture alert pop-ups?**
A: Check if your terminal app has Accessibility permission (System Settings → Privacy & Security → Accessibility).

**Q: Auto-pause not pausing video?**
A: 1) Check Accessibility and Automation permissions; 2) Chrome/Safari/Arc support background tab control, Firefox only supports foreground tab.

**Q: Installed but tmux session not starting?**
A: Run `bash service.sh status` to check, `bash service.sh start` to manually start.

## Tech Stack

- Python 3.12 + MediaPipe Pose + OpenCV
- macOS: rumps tray + osascript notifications + say TTS
- Windows: pystray tray + winotify notifications + pyttsx3 TTS
- Cloud: Supabase (PostgreSQL + Auth + REST API) + httpx
- Icons: Pillow dynamic posture indicator icons
- Packaging: PyInstaller (macOS .app / Windows .exe) + Homebrew Formula + Apple notarization
- CI/CD: GitHub Actions cross-platform build + auto-release

## Version History

### v1.3.0
- Dynamic tray icons: icon shape and color change based on specific posture issues (neck forward / head tilt / uneven shoulders / torso lean)
- Added head tilt detection metric
- DMG installer, Apple signed + notarized, download and use

### v1.2.0
- Fixed slow/stuck monitoring stop
- Homebrew install support (`brew install zoubenjia/tap/sit-monitor`)
- `brew services` auto-start support
- Apple code signing + notarization (entitlements)

### v1.1.0
- Standing desk posture monitoring, three switchable modes
- Google OAuth login
- Push-up battle feature
- Fatigue detection (blink rate, yawning)
- Chinese/English bilingual support

## License

MIT

---

# Sit Position — 坐姿监控 & 运动教练

用摄像头实时检测坐姿/站姿、语音引导俯卧撑训练。支持 macOS 和 Windows 10/11。支持中文/英文双语切换。

<p align="center">
  <img src="docs/demo_zh.gif" alt="Sit Monitor 演示" width="600">
</p>

## 功能

### 坐姿/站姿监控
- **姿势检测** — 肩膀倾斜、头部前倾、头部侧倾、躯干前倾四项指标，坐姿站姿通用
- **动态图标** — 托盘图标实时反映具体姿势问题：颈前倾/头侧倾/肩不平/躯干前倾各有不同变形和颜色
- **站立办公支持** — 三种模式：自动检测 / 坐姿 / 站姿，托盘菜单一键切换
- **弹窗提醒** — 持续坏姿势自动弹窗，可调阈值和时长
- **正向反馈** — 纠正姿势后语音鼓励；连续保持好姿势 15/30/60/120 分钟时播报里程碑鼓励
- **久坐/久站提醒** — 连续就坐或站立超过 45 分钟弹窗提醒活动休息（可调时长）
- **离开暂停** — 人离开摄像头自动暂停浏览器视频，回来自动恢复（支持 Chrome/Safari/Arc/Firefox 等）
- **会议兼容** — 视频会议占用摄像头时自动让出，结束后重连
- **开机自启** — 一条命令安装后台服务

### 俯卧撑训练
- **语音引导就位** — 分步引导：放电脑→站位→趴下→就绪
- **实时计数** — 中文语音播报"一、二、三..."
- **姿势纠正** — 臀部下沉/翘起、下降不够深、头部下垂
- **自动结束** — 站起来即结束训练，播报总结
- **训练记录** — 数据写入 `logs/exercise.jsonl`，可通过 MCP 查询

### 俯卧撑对战
- **快速对战** — 一键从排行榜选择对手发起俯卧撑 PK
- **质量加权评分** — `score = reps × (0.7 + 0.3 × good_reps / reps)`，鼓励质量但不压制数量
- **异步模式** — 双方各自完成，不需同时在线，都完成后自动判定胜负
- **动作分级** — 每个 rep 自动判定 good / shallow / bad，计入对战评分
- **对战成就** — 初次对战、胜利者、三连胜

### 排行榜 & 社交互动（云端，可选）
- **日/周排行榜** — 按良好率排名，与其他用户比拼坐姿成绩
- **成就系统** — 13 个徽章，含专注半小时/一小时达人/钢铁意志（连续好姿势）、连胜、对战等
- **点赞鼓励** — 在排行榜上给其他用户的日报点赞
- **好友挑战** — 向其他用户发起坐姿 PK（良好率 / 监控时长）
- **Google 登录** — 可选绑定 Google 账号，多设备同步数据，随时解绑恢复匿名
- **隐私可控** — 默认关闭，需手动开启；数据分享可随时关闭
- **零门槛** — 无需注册账号，设备自动绑定身份，设置昵称即可

### 多语言支持 (i18n)
- **中文/英文双语** — 菜单、通知、语音播报、报告全面本地化
- **一键切换** — 托盘菜单底部点击 🌐 English / 🌐 中文 即时切换
- **TTS 语音自适应** — 中文用 Tingting，英文用 Samantha（macOS）
- **易于扩展** — 纯 Python 字典实现，添加新语言只需新建一个 `.py` 文件

### 简单 / 进阶模式
- **简单模式**（默认）— 只显示监控、训练、对战、统计，新用户一目了然
- **进阶模式** — 完整设置、社交、账号管理，点击菜单底部切换

## 系统要求

### macOS
- macOS 13+ (Ventura 或更新)
- MacBook 内置摄像头或外接摄像头
- tmux（后台运行需要，`brew install tmux`）

### Windows
- Windows 10/11
- 摄像头（内置或外接）
- Python 3.12+（安装时勾选 "Add Python to PATH"）

### 权限设置

#### macOS 权限

**1. 摄像头权限（必须）**

你的终端应用（iTerm2 / Terminal）需要摄像头访问权限：

> 系统设置 → 隐私与安全性 → 摄像头 → 勾选你的终端应用

如果列表中没有你的终端应用，首次运行程序时系统会自动弹窗请求。如果不小心拒绝了，需要手动到上述设置中开启。

**2. 辅助功能权限（auto-pause 功能需要）**

使用 `--auto-pause` 自动暂停视频功能时，需要允许终端控制其他应用：

> 系统设置 → 隐私与安全性 → 辅助功能 → 勾选你的终端应用

**3. 自动化权限（auto-pause 功能需要）**

首次触发视频暂停时，系统会询问是否允许终端控制浏览器，选择"允许"即可。

> 如果权限设置后仍然不生效，尝试重启终端应用。

#### Windows 权限

首次运行时系统会弹窗请求摄像头权限，点击"允许"即可。

> 设置 → 隐私 → 摄像头 → 允许应用访问摄像头

## 安装

### 方式一：下载二进制（最简单）

从 [GitHub Releases](https://github.com/zoubenjia/sit-position/releases/latest) 下载：

- **macOS**：`SitMonitor-macOS.dmg` — 打开后拖入 Applications 即可。已通过 Apple 代码签名 + 公证，Gatekeeper 不会拦截。
- **Windows**：`SitMonitor-Windows.zip` — 解压后运行 `SitMonitor.exe`，无需安装 Python。

### 方式二：Homebrew（推荐，macOS）

```bash
brew tap zoubenjia/tap
brew install sit-monitor

# 启动菜单栏模式
sit-monitor --tray

# 开机自启
brew services start sit-monitor
```

### 方式三：pip 安装

```bash
pip install git+https://github.com/zoubenjia/sit-position.git

# 需要手动下载模型文件
curl -sSL -o pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

### 方式四：从源码运行

**没装 Git？** 直接[下载 ZIP](https://github.com/zoubenjia/sit-position/archive/refs/heads/main.zip)，解压后进入文件夹运行 setup 即可。

#### macOS

```bash
git clone https://github.com/zoubenjia/sit-position.git
cd sit-position
bash setup.sh    # 一键搭建环境 + 安装自启动 + 启动托盘
```

#### Windows

```powershell
git clone https://github.com/zoubenjia/sit-position.git
cd sit-position
powershell -ExecutionPolicy Bypass -File setup.ps1    # 一键搭建环境 + 安装自启动 + 启动托盘
```

> **PowerShell 被禁用？** 使用 `.bat` 替代方案：`setup.bat`

## 后台服务

### macOS

```bash
bash service.sh install   # 安装自启动
bash service.sh start     # 启动
bash service.sh stop      # 停止
bash service.sh status    # 查看状态
bash service.sh update    # 从远程仓库更新
bash service.sh log       # 查看日志
```

### Windows (PowerShell)

```powershell
.\service.ps1 install     # 安装自启动 + 启动
.\service.ps1 start       # 启动
.\service.ps1 stop        # 停止
.\service.ps1 restart     # 重启
.\service.ps1 status      # 查看状态
.\service.ps1 update      # 从远程仓库更新
.\service.ps1 log         # 查看日志
.\service.ps1 uninstall   # 卸载自启动
```

### Windows (CMD — PowerShell 被禁用时)

```cmd
service.bat install       & REM 安装自启动 + 启动
service.bat start         & REM 启动
service.bat stop          & REM 停止
service.bat restart       & REM 重启
service.bat status        & REM 查看状态
service.bat update        & REM 从远程仓库更新
service.bat log           & REM 查看日志
service.bat uninstall     & REM 卸载自启动
```

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--camera` | 0 | 摄像头索引 |
| `--interval` | 5.0 | 检测间隔（秒） |
| `--bad-seconds` | 30 | 触发提醒的连续坏姿势时长 |
| `--cooldown` | 180 | 两次提醒最小间隔 |
| `--auto-pause` | off | 离开时自动暂停视频 |
| `--away-seconds` | 3.0 | 离开多久后暂停 |
| `--shoulder-threshold` | 10° | 肩膀倾斜阈值 |
| `--neck-threshold` | 15° | 头部前倾阈值 |
| `--torso-threshold` | 8° | 躯干前倾阈值 |
| `--debug` | off | 显示摄像头画面和骨架 |

## 云端社交（可选）

社交功能默认关闭，开启方式：

1. 托盘菜单点击 **"Enable Cloud"**
2. 设置昵称（托盘 → Social → Nickname）
3. 排行榜、成就、挑战等功能自动可用

云端使用 Supabase 免费服务，数据仅包含坐姿统计（良好率、时长），不含任何图像或个人信息。可随时通过 **"Share Data"** 开关关闭数据共享。

### MCP 工具

通过 AI 助手（Claude 等）可使用以下 MCP 工具：

| 工具 | 说明 |
|------|------|
| `social_leaderboard` | 查看日/周排行榜 |
| `social_my_achievements` | 查看成就列表 |
| `social_send_like` | 给其他用户点赞 |
| `social_create_challenge` | 发起坐姿挑战 |
| `social_my_challenges` | 查看挑战列表 |
| `social_profile` | 查看社交资料 |
| `battle_create` | 创建俯卧撑对战 |
| `battle_accept` | 接受对战邀请 |
| `battle_cancel` | 取消对战 |
| `battle_list` | 列出我的对战 |
| `battle_details` | 查看对战详情 |
| `battle_start_exercise` | 开始对战运动 |
| `auth_status` | 查看认证状态 |
| `auth_link_google` | 绑定 Google 账号 |
| `auth_unlink_provider` | 解绑社交账号 |

## 隐私声明

**你的隐私是第一优先级。**

- 所有图像处理在**本地设备**上完成，摄像头画面**不保存、不录制**
- 程序只计算关节角度数值，**不存储任何图像**
- 云端社交功能**默认关闭**，开启后仅上传坐姿统计数据（良好率、时长）
- 可随时关闭数据共享，关闭后不再上传任何数据
- 不收集任何个人信息
- Google 登录可选绑定，仅获取昵称和头像，随时可解绑
- OAuth 回调使用随机端口 + state 参数验证，防止 CSRF
- 代码完全开源，可自行审查

## 常见问题

**Q: 运行后提示"摄像头被占用"？**
A: 可能正在视频会议，程序会自动等待摄像头释放，会议结束后自动恢复监控。

**Q: 没有收到坐姿提醒弹窗？**
A: 检查终端应用是否有辅助功能权限（系统设置 → 隐私与安全性 → 辅助功能）。

**Q: auto-pause 没有暂停视频？**
A: 1) 检查辅助功能和自动化权限；2) Chrome/Safari/Arc 支持后台 tab 控制，Firefox 仅支持前台 tab。

**Q: 安装了但 tmux session 没启动？**
A: 运行 `bash service.sh status` 查看状态，`bash service.sh start` 手动启动。

## 技术栈

- Python 3.12 + MediaPipe Pose + OpenCV
- macOS: rumps 托盘 + osascript 通知 + say TTS
- Windows: pystray 托盘 + winotify 通知 + pyttsx3 TTS
- 云端: Supabase (PostgreSQL + Auth + REST API) + httpx
- 图标: Pillow 动态生成姿势指示图标
- 打包: PyInstaller (macOS .app / Windows .exe) + Homebrew Formula + Apple 公证
- CI/CD: GitHub Actions 跨平台构建 + 自动发布

## 版本历史

### v1.3.0
- 动态托盘图标：根据具体姿势问题（颈前倾/头侧倾/肩不平/躯干前倾）显示不同图标变形和颜色
- 新增头部侧倾检测指标
- DMG 安装方式，Apple 签名 + 公证，下载即用

### v1.2.0
- 修复监控 stop 响应慢/卡死问题
- 支持 Homebrew 安装（`brew install zoubenjia/tap/sit-monitor`）
- 支持 `brew services` 开机自启
- Apple 代码签名 + 公证支持（entitlements）

### v1.1.0
- 支持站立办公姿势监控，三种模式可切换
- Google OAuth 登录
- 俯卧撑对战功能
- 疲劳检测（眨眼率、打哈欠）
- 中英文双语支持

## License

MIT
