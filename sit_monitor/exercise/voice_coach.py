"""语音教练引擎：优先级队列 + 分类冷却，后台 daemon 线程顺序播放"""

import heapq
import subprocess
import sys
import threading
import time

from sit_monitor.tts import speak


class VoiceCoach:
    """后台语音播放引擎，支持打断当前语音。

    优先级: 0=关键（计数、就位引导），1=姿势纠正，2=鼓励
    分类冷却: 同 category 5 秒内不重复；priority 0 不受限
    队列上限 5，满时丢弃低优先级项
    interrupt: 新消息到来时打断正在播放的语音
    """

    QUEUE_MAX = 5
    COOLDOWN = 5.0  # 同类别冷却秒数

    def __init__(self):
        self._queue: list[tuple[int, float, str, str]] = []  # (priority, seq, text, category)
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._cooldowns: dict[str, float] = {}  # category -> last_play_time
        self._running = True
        self._seq = 0
        self._current_proc: subprocess.Popen | None = None  # 正在播放的进程

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def say(self, text: str, priority: int = 0, category: str = "", interrupt: bool = False):
        """将语音加入播放队列。

        Args:
            text: 要播报的文字
            priority: 0=关键, 1=姿势纠正, 2=鼓励
            category: 分类标识，同类 5 秒内不重复（priority 0 不受限）
            interrupt: 是否打断正在播放的语音
        """
        now = time.time()

        # 分类冷却检查（priority 0 不受限）
        if priority > 0 and category:
            with self._lock:
                last = self._cooldowns.get(category, 0)
                if now - last < self.COOLDOWN:
                    return

        with self._lock:
            # 队列满时丢弃最低优先级（数字最大）的项
            if len(self._queue) >= self.QUEUE_MAX:
                worst_idx = max(range(len(self._queue)), key=lambda i: self._queue[i][0])
                if self._queue[worst_idx][0] <= priority:
                    return
                self._queue.pop(worst_idx)
                heapq.heapify(self._queue)

            self._seq += 1
            heapq.heappush(self._queue, (priority, self._seq, text, category))

        # 打断当前正在播放的语音
        if interrupt:
            self._kill_current()

        self._event.set()

    def clear(self):
        """清空队列并打断当前语音。"""
        with self._lock:
            self._queue.clear()
        self._kill_current()

    def stop(self):
        self._running = False
        self._kill_current()
        self._event.set()

    def _kill_current(self):
        """终止正在播放的 say 进程。"""
        proc = self._current_proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _worker(self):
        while self._running:
            self._event.wait(timeout=1.0)
            self._event.clear()

            while self._running:
                with self._lock:
                    if not self._queue:
                        break
                    priority, _seq, text, category = heapq.heappop(self._queue)

                # 再次检查冷却
                now = time.time()
                if priority > 0 and category:
                    with self._lock:
                        last = self._cooldowns.get(category, 0)
                        if now - last < self.COOLDOWN:
                            continue

                # 播放语音
                try:
                    proc = speak(text, blocking=False)
                    if proc is not None:
                        # macOS: 返回 Popen，可被 terminate 打断
                        self._current_proc = proc
                        proc.wait()
                        self._current_proc = None
                    else:
                        # Windows: pyttsx3 阻塞播放，已在 speak() 内完成
                        pass
                except Exception:
                    self._current_proc = None

                # 更新冷却时间
                if category:
                    with self._lock:
                        self._cooldowns[category] = time.time()
