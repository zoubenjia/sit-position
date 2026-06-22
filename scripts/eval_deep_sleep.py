#!/usr/bin/env python3
"""离线评估深度休眠效果：读 deepsleep_events.jsonl + posture.jsonl，输出报告。

省电侧：累计休眠时长、会话数、posture 检测密度（每小时条数）。
误进入侧：进入后 <30s 即退出的会话数（疑似睡早）。
不依赖运行中进程，可随时跑。
"""
import json
import os
import sys


def summarize(events, posture_count_by_hour):
    """聚合事件，返回评估指标 dict。"""
    sessions = 0
    total_sleep = 0.0
    short_exits = 0  # 进入后 <30s 即退出（疑似睡早了）
    for e in events:
        if e.get("event") == "deep_sleep_exit":
            sessions += 1
            dur = float(e.get("duration_s", 0.0))
            total_sleep += dur
            if dur < 30:
                short_exits += 1
    return {
        "sessions": sessions,
        "total_sleep_seconds": total_sleep,
        "short_exits": short_exits,
        "posture_count_by_hour": posture_count_by_hour,
    }


def _read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    return out


def _posture_by_hour(records):
    by_hour = {}
    for r in records:
        ts = r.get("ts", "")
        hour = ts[:13]  # 'YYYY-MM-DDTHH'
        if hour:
            by_hour[hour] = by_hour.get(hour, 0) + 1
    return by_hour


def main():
    log_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    events = _read_jsonl(os.path.join(log_dir, "deepsleep_events.jsonl"))
    posture = _read_jsonl(os.path.join(log_dir, "posture.jsonl"))
    r = summarize(events, _posture_by_hour(posture))
    print(f"深度休眠会话数: {r['sessions']}")
    print(f"累计休眠时长: {r['total_sleep_seconds']/3600:.2f} 小时")
    print(f"疑似睡早(进入<30s 即退出)次数: {r['short_exits']}")
    hours = sorted(r["posture_count_by_hour"])
    if hours:
        vals = [r["posture_count_by_hour"][h] for h in hours]
        print(f"posture 检测密度: {len(hours)} 小时, 每小时均值 {sum(vals)/len(vals):.0f} 条")


if __name__ == "__main__":
    main()
