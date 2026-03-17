#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股做T智能分析工具 - 做T收益追踪模块
记录每日建议买卖价，自动对比实际收盘价，计算准确率
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd


class TTracker:
    """做T收益追踪器"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.records: List[Dict] = []
        self._load()

    def _get_file_path(self) -> str:
        return os.path.join(self.data_dir, "t_records.json")

    def _load(self):
        """加载历史记录"""
        path = self._get_file_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.records = json.load(f)

    def _save(self):
        """保存记录"""
        path = self._get_file_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    def add_record(
        self,
        stock_code: str,
        date: str,
        buy_price: float,
        sell_price: float,
        actual_low: float = None,
        actual_high: float = None,
        actual_close: float = None,
    ) -> Dict:
        """
        添加做T记录
        :param stock_code: 股票代码
        :param date: 日期 YYYY-MM-DD
        :param buy_price: 建议买入价
        :param sell_price: 建议卖出价
        :param actual_low: 当日实际最低价
        :param actual_high: 当日实际最高价
        :param actual_close: 当日实际收盘价
        :return: 记录（含计算结果）
        """
        record = {
            "stock_code": stock_code,
            "date": date,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "actual_low": actual_low,
            "actual_high": actual_high,
            "actual_close": actual_close,
            "timestamp": datetime.now().isoformat(),
        }

        # 计算结果
        t_space = sell_price - buy_price
        t_space_pct = (t_space / buy_price) * 100

        record["t_space"] = round(t_space, 2)
        record["t_space_pct"] = round(t_space_pct, 2)

        # 验证建议是否有效
        if actual_low and actual_high:
            # 买入建议：实际最低价是否达到建议买入区间
            buy_hit = actual_low <= buy_price * 1.01  # 实际价格接近建议价就算命中
            # 卖出建议：实际最高价是否达到建议卖出区间
            sell_hit = actual_high >= sell_price * 0.99
            # 双向都命中 = 完美做T机会
            perfect_t = buy_hit and sell_hit

            record["buy_hit"] = buy_hit
            record["sell_hit"] = sell_hit
            record["perfect_t"] = perfect_t

            if perfect_t:
                # 理论最大收益
                record["max_profit_pct"] = round(
                    (sell_price - buy_price) / buy_price * 100, 2
                )
                record["max_profit_per_10k"] = round(
                    (sell_price - buy_price) / buy_price * 10000, 2
                )

        self.records.append(record)
        self._save()
        return record

    def get_stats(self, stock_code: str = None, days: int = 30) -> Dict:
        """
        获取做T统计数据
        :param stock_code: 股票代码（None 则统计全部）
        :param days: 统计天数
        :return: 统计结果
        """
        filtered = [
            r for r in self.records if stock_code is None or r["stock_code"] == stock_code
        ]

        if not filtered:
            return {"total_records": 0}

        # 基础统计
        total = len(filtered)
        with_validation = [r for r in filtered if r.get("buy_hit") is not None]
        buy_hit_count = sum(1 for r in with_validation if r.get("buy_hit"))
        sell_hit_count = sum(1 for r in with_validation if r.get("sell_hit"))
        perfect_t_count = sum(1 for r in with_validation if r.get("perfect_t"))

        avg_t_space = (
            sum(r["t_space_pct"] for r in filtered) / total if total > 0 else 0
        )

        # 月度汇总
        monthly_profit = 0
        for r in with_validation:
            if r.get("perfect_t") and r.get("max_profit_per_10k"):
                monthly_profit += r["max_profit_per_10k"]

        stats = {
            "total_records": total,
            "validated_records": len(with_validation),
            "buy_hit_rate": (
                round(buy_hit_count / len(with_validation) * 100, 1)
                if with_validation
                else 0
            ),
            "sell_hit_rate": (
                round(sell_hit_count / len(with_validation) * 100, 1)
                if with_validation
                else 0
            ),
            "perfect_t_rate": (
                round(perfect_t_count / len(with_validation) * 100, 1)
                if with_validation
                else 0
            ),
            "perfect_t_count": perfect_t_count,
            "avg_t_space_pct": round(avg_t_space, 2),
            "est_monthly_profit_per_10k": round(monthly_profit, 2),
        }

        return stats

    def get_report(self, days: int = 30) -> str:
        """生成文字报告"""
        stats = self.get_stats(days=days)

        if stats["total_records"] == 0:
            return "暂无做T记录，开始使用后系统将自动追踪收益。"

        lines = [
            f"📊 做T收益追踪报告",
            f"📅 统计周期: 最近{days}天",
            f"📝 总记录数: {stats['total_records']}",
            "",
            f"🎯 建议准确率:",
            f"   买入命中: {stats['buy_hit_rate']}% ({stats['validated_records']}条验证)",
            f"   卖出命中: {stats['sell_hit_rate']}%",
            f"   完美做T: {stats['perfect_t_rate']}% ({stats['perfect_t_count']}次)",
            "",
            f"💰 收益估算 (按1万元本金):",
            f"   平均做T空间: {stats['avg_t_space_pct']}%",
            f"   月度预估收益: ¥{stats['est_monthly_profit_per_10k']}",
        ]

        # 每只股票单独统计
        stocks = set(r["stock_code"] for r in self.records)
        if len(stocks) > 1:
            lines.append("")
            lines.append("📈 分股统计:")
            for code in stocks:
                s = self.get_stats(stock_code=code, days=days)
                lines.append(
                    f"   {code}: 命中率{s['buy_hit_rate']}% | 完美做T {s['perfect_t_count']}次"
                )

        return "\n".join(lines)

    def export_csv(self, filepath: str = "data/t_records.csv"):
        """导出为 CSV"""
        if not self.records:
            return
        df = pd.DataFrame(self.records)
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        return filepath


if __name__ == "__main__":
    # 演示
    tracker = TTracker()

    # 模拟添加记录
    tracker.add_record(
        stock_code="sh600791",
        date="2026-03-17",
        buy_price=16.20,
        sell_price=16.80,
        actual_low=16.15,
        actual_high=16.85,
        actual_close=16.65,
    )

    print(tracker.get_report())
