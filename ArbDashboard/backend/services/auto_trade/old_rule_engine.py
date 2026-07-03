# -*- coding: utf-8 -*-
"""
自动化交易规则引擎 V2.0
支持基金/分类筛选、折溢价阈值、仓位与资金量控制。
"""
import json
import os
import uuid
import logging

logger = logging.getLogger(__name__)

RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json")

class RuleEngine:
    def __init__(self):
        self.rules = []
        self.load_rules()

    def load_rules(self):
        if os.path.exists(RULES_FILE):
            try:
                with open(RULES_FILE, 'r', encoding='utf-8') as f:
                    self.rules = json.load(f) or []
            except Exception as e:
                logger.error(f"加载规则文件失败: {e}")
                self.rules = []
        else:
            self.rules = []

    def save_rules(self):
        try:
            with open(RULES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存规则文件失败: {e}")

    def add_rule(self, rule_data):
        """
        新增规则
        rule_data 示例: {
            "name": "高频折价猎手",
            "target": "162411", # 或 "黄金原油"
            "type": "code", # "code" | "category"
            "indicator": "discount", # "discount" | "premium"
            "threshold": 0.7,
            "action": "BUY",
            "mode": "semi-auto", # "manual" | "semi-auto" | "full-auto"
            "max_pos_wan": 50, # 最大持仓 50万份
            "order_vol": 2000, # 单笔 2000股
            "capital_limit_wan": 10 # 投入资金上限 10万
        }
        """
        rule_data['id'] = str(uuid.uuid4())
        rule_data['enabled'] = False # 默认不开启，需手动激活
        self.rules.append(rule_data)
        self.save_rules()
        return rule_data['id']

    def update_rule(self, rule_id, update_data):
        for r in self.rules:
            if r['id'] == rule_id:
                r.update(update_data)
                self.save_rules()
                return True
        return False

    def delete_rule(self, rule_id):
        self.rules = [r for r in self.rules if r['id'] != rule_id]
        self.save_rules()

    def get_active_rules(self):
        return [r for r in self.rules if r.get('enabled', False)]
