# -*- coding: utf-8 -*-
"""
SignalDetector — 信号检测引擎
--------------------------------
每 10 秒轮询活跃规则，检查实时折溢价是否达到阈值。
命中时记录日志供用户参考，不下单、不执行任何交易操作。
"""
import threading
import time
import logging
from collections import deque
from datetime import datetime

logger = logging.getLogger("SignalDetector")

class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=200):
        super().__init__()
        self.logs = deque(maxlen=capacity)

    def emit(self, record):
        self.logs.appendleft({
            "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage()
        })

logger.setLevel(logging.INFO)
_mem_handler = MemoryLogHandler()
if not any(isinstance(h, MemoryLogHandler) for h in logger.handlers):
    logger.addHandler(_mem_handler)


class SignalDetector:
    def __init__(self):
        self.running = False
        self.thread = None
        self.rule_engine = None
        self.fund_service = None

        self.COOLDOWN = 300
        self._last_signal = {}

    def inject(self, rule_engine=None, fund_service=None):
        if rule_engine:
            self.rule_engine = rule_engine
        if fund_service:
            self.fund_service = fund_service
        logger.info("[SignalDetector] 依赖注入完成")

    def get_recent_logs(self):
        return list(_mem_handler.logs)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("[SignalDetector] 信号检测已启动（每 10 秒扫描一轮）")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("[SignalDetector] 信号检测已停止")

    def _loop(self):
        while self.running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"[SignalDetector] 异常: {e}")
            time.sleep(10)

    def _tick(self):
        if not self.rule_engine or not self.fund_service:
            return
        active = self.rule_engine.get_active_rules() or []
        if not active:
            return

        for rule in active:
            rule_id = rule.get("id")
            fund_code = rule.get("target", "")
            indicator = rule.get("indicator", "discount")
            threshold = float(rule.get("threshold", 0.7))

            if not fund_code:
                continue

            now = time.time()
            last = self._last_signal.get(rule_id, 0)
            if now - last < self.COOLDOWN:
                continue

            meta = self._get_premium(fund_code)
            if meta is None:
                continue
            premium = meta.get("rt_premium", meta.get("premium", 0))

            is_hit = False
            if indicator == "discount":
                if premium < -threshold:
                    is_hit = True
            else:
                if premium > threshold:
                    is_hit = True

            if not is_hit:
                continue

            self._last_signal[rule_id] = now
            logger.info(f"信号触发 [{rule.get('name')}] {fund_code} "
                        f"当前{indicator}={premium:.2f}%（阈值{threshold}%）")

    def _get_premium(self, fund_code):
        try:
            data = self.fund_service.get_valuation_meta(fund_code)
            if data and isinstance(data, dict):
                return data
        except Exception as e:
            logger.debug(f"get_premium 失败 {fund_code}: {e}")
        return None


# 全局单例
signal_detector = SignalDetector()
