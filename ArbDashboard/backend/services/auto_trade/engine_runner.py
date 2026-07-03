# -*- coding: utf-8 -*-
"""
自动化交易执行引擎 (守护线程)
定时循环检测实时价格，评估规则，记录日志，并驱动真实交易通道。
"""
import threading
import time
import logging
import requests
import pandas as pd
from datetime import datetime
from collections import deque
# [AI-2026-07-02] 已重命名为 old_rule_engine.py 避免与 private/rule_engine.py (DB驱动版) 冲突
from .old_rule_engine import RuleEngine

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

logger = logging.getLogger("AutoTradeEngine")
logger.setLevel(logging.INFO)

memory_handler = MemoryLogHandler()

if not any(isinstance(h, MemoryLogHandler) for h in logger.handlers):
    logger.addHandler(memory_handler)

class AutoTradeRunner:
    def __init__(self):
        self.engine = RuleEngine()
        self.running = False
        self.thread = None
        self.db = None 
        self.trade_service = None # 将由外部注入
        self.market_service = None # 行情源服务

        # 核心开关：是否允许真实报单 (True 则真实发单，False 则模拟记录日志)
        self.REAL_ORDER_ENABLED = True 

        # 冷却时间字典
        self.cooldowns = {}
        self.COOLDOWN_SECONDS = 300 # 5分钟冷却

    def get_recent_logs(self):
        return list(memory_handler.logs)

    def start(self):
        if self.running: return
        self.running = True
        
        # [V4.6] 严禁自动救活 TradingService，防止 TDX 冲突
        # if not self.trade_service and self.db:
        #     from services.trading_service import TradingService
        #     self.trade_service = TradingService(self.db)
            
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("[AutoTrade] 自动交易引擎已进入待命模式 (已切断交易通道)")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("[AutoTrade] 自动交易引擎已停止")

    def _run_loop(self):
        while self.running:
            try:
                # [V4.4] 防御性处理：确保 active_rules 为列表
                active_rules = self.engine.get_active_rules() or []
                if not active_rules:
                    time.sleep(5.0)
                    continue

                # 1. 同步最新持仓
                if not self.trade_service:
                    time.sleep(2.0); continue
                
                pos_list = self.trade_service.get_positions()
                positions = {p['code']: p for p in pos_list}
                
                # 2. 遍历规则评估
                for rule in active_rules:
                    rule_id = rule.get('id')
                    code = rule.get('code') or rule.get('target')
                    
                    if not code:
                        logger.error(f"[AutoTrade] [Error] 规则 {rule_id} 缺失品种代码 (code/target)")
                        continue
                    
                    # 冷却检查
                    now = time.time()
                    if now - self.cooldowns.get(rule_id, 0) < self.COOLDOWN_SECONDS:
                        continue

                    # 3. 信号计算 (这里需要计算实时折溢价)
                    # 简化：目前先复用现有的跌幅/涨幅逻辑，后续可扩展为基于 rt_val 的精确溢价
                    rt_price = 0
                    if self.market_service:
                        quote = self.market_service.get_realtime_quote(code)
                        rt_price = quote.get('price', 0) if quote else 0
                    
                    if rt_price <= 0: continue

                    # [判定逻辑] 示例：折价买入
                    is_triggered = False
                    trigger_msg = ""
                    
                    # 获取该基金当前持仓
                    current_vol = positions.get(code, {}).get('volume', 0)
                    
                    if rule.get('action') == 'BUY':
                        # ... 接入折溢价判定逻辑 ...
                        pass # 预留位置
                    
                    # 4. 执行报单
                    if is_triggered:
                        logger.info(f"[AutoTrade] [Signal] 命中规则: {rule['name']}")
                        if self.REAL_ORDER_ENABLED:
                            res = self.trade_service.execute_order(
                                action=rule['action'],
                                code=code,
                                volume=rule['order_volume'],
                                price=rt_price
                            )
                            if res['status'] == 'ok':
                                logger.info(f"[AutoTrade] [OK] 自动报单成功: {res['message']}")
                                self.cooldowns[rule_id] = now
                            else:
                                logger.error(f"[AutoTrade] [Error] 自动报单失败: {res['message']}")
                        else:
                            logger.info(f"[AutoTrade] 发现机会但未开启真实下单: {rule['name']}")

            except Exception as e:
                logger.error(f"[AutoTrade] [Exception] 引擎循环异常: {e}")
            
            time.sleep(5.0)

auto_trade_runner = AutoTradeRunner()
