# Sit Position — 坐姿监控 & 运动教练

用摄像头实时检测坐姿、语音引导俯卧撑训练。支持 macOS 和 Windows 10/11。

## 功能

### 坐姿监控
- **坐姿检测** — 肩膀倾斜、头部前倾、躯干前倾三项指标
- **弹窗提醒** — 持续坏姿势自动弹窗，可调阈值和时长
- **正向反馈** — 纠正坐姿后语音鼓励"坐姿很好，继续保持"
- **久坐提醒** — 连续就坐超过 45 分钟弹窗提醒起来活动、喝杯水（可调时长）
- **离开暂停** — 人离开摄像头自动暂停浏览器视频，回来自动恢复（支持 Chrome/Safari/Arc/Firefox 等）
- **会议兼容** — 视频会议占用摄像头时自动让出，结束后重连
- **开机自启** — 一条命令安装后台服务

### 俯卧撑训练
- **语音引导就位** — 分步引导：放电脑→站位→趴下→就绪
- **实时计数** — 中文语音播报"一、二、三..."
- **姿势纠正** — 臀部下沉/翘起、下降不够深、头部下垂
- **自动结束** — 站起来即结束训练，播报总结
- **训练记录** — 数据写入 `logs/exercise.jsonl`，可通过 MCP 查询

### 排行榜 & 社交互动（云端，可选）
- **日/周排行榜** — 按良好率排名，与其他用户比拼坐姿成绩
- **成就系统** — 7 个徽章（初次打卡、三日连胜、周冠军、完美一天、百小时达人、社交蝴蝶、早起鸟儿）
- **点赞鼓励** — 在排行榜上给其他用户的日报点赞
- **好友挑战** — 向其他用户发起坐姿 PK（良好率 / 监控时长）
- **隐私可控** — 默认关闭，需手动开启；数据分享可随时关闭
- **零门槛** — 无需注册账号，设备自动绑定身份，设置昵称即可

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

## 快速开始

**没装 Git？** 直接[下载 ZIP](https://github.com/zoubenjia/sit-position/archive/refs/heads/main.zip)，解压后进入文件夹运行 setup 即可。

### macOS

```bash
git clone https://github.com/zoubenjia/sit-position.git
cd sit-position
bash setup.sh    # 一键搭建环境 + 安装自启动 + 启动托盘
```

### Windows

```powershell
git clone https://github.com/zoubenjia/sit-position.git
cd sit-position
powershell -ExecutionPolicy Bypass -File setup.ps1    # 一键搭建环境 + 安装自启动 + 启动托盘
```

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

### Windows

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

### MCP 社交工具

通过 AI 助手（Claude 等）可使用以下 MCP 工具：

| 工具 | 说明 |
|------|------|
| `social_leaderboard` | 查看日/周排行榜 |
| `social_my_achievements` | 查看成就列表 |
| `social_send_like` | 给其他用户点赞 |
| `social_create_challenge` | 发起坐姿挑战 |
| `social_my_challenges` | 查看挑战列表 |
| `social_profile` | 查看社交资料 |

## 隐私声明

**你的隐私是第一优先级。**

- 所有图像处理在**本地设备**上完成，摄像头画面**不保存、不录制**
- 程序只计算关节角度数值，**不存储任何图像**
- 云端社交功能**默认关闭**，开启后仅上传坐姿统计数据（良好率、时长）
- 可随时关闭数据共享，关闭后不再上传任何数据
- 不收集任何个人信息
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

## License

MIT
