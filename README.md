# Sit Position — MacBook 坐姿监控

用 MacBook 内置摄像头实时检测坐姿，坏姿势持续 30 秒弹窗提醒，离开座位自动暂停视频。

## 功能

- **坐姿检测** — 肩膀倾斜、头部前倾、躯干前倾三项指标
- **弹窗提醒** — 持续坏姿势自动弹窗，可调阈值和时长
- **离开暂停** — 人离开摄像头自动暂停 Firefox 视频，回来自动恢复
- **会议兼容** — 视频会议占用摄像头时自动让出，结束后重连
- **开机自启** — 一条命令安装后台服务

## 快速开始

```bash
git clone https://github.com/zoubenjia/sit-position.git
cd sit-position
bash setup.sh                     # 搭建环境（Python 3.12 + 依赖 + 模型）
source .venv/bin/activate
python sit_monitor.py --debug     # debug 模式验证
python sit_monitor.py --auto-pause  # 正式使用
```

## 后台服务

```bash
bash service.sh install   # 安装自启动
bash service.sh start     # 启动
bash service.sh stop      # 停止
bash service.sh status    # 查看状态
bash service.sh update    # 从 GitHub 更新
bash service.sh log       # 查看日志
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

## 隐私声明

**你的隐私是第一优先级。**

- 所有图像处理在**本地设备**上完成，**不联网、不上传**任何数据
- 摄像头画面**不保存、不录制**，每帧处理后立即丢弃
- 程序只计算关节角度数值，**不存储任何图像**
- 不收集任何个人信息
- 代码完全开源，可自行审查

## 技术栈

- Python 3.12 + MediaPipe Pose + OpenCV
- macOS osascript 弹窗通知
- tmux 后台运行

## License

MIT
