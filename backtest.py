#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股做T智能分析工具 - 回测验证模块 v1.3
用历史数据回测做T建议的准确率，验证买卖信号的有效性。

验证逻辑：
- 买入建议：触发后 N 日内是否出现更低价格（有则说明"还可以更便宜"，建议偏早）
- 卖出建议：触发后 N 日内是否出现更高价格（有则说明"卖早了"，建议偏早）
- 理想目标：买入后不再下跌、卖出后不再上涨
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from technical import StockDataFetcher, TechnicalAnalyzer


class Backtester:
    """做T信号回测器"""

    def __init__(self, stock_code: str):
        self.stock_code = stock_code
        self.fetcher = StockDataFetcher()

    def run(
        self,
        days: int = 60,
        forward_days: int = 3,
    ) -> Dict:
        """
        执行回测
        :param days: 回测用的历史数据天数（额外加30天作为技术指标预热期）
        :param forward_days: 信号触发后向前看的天数（默认3天）
        :return: 回测结果字典
        """
        # 多取30天作为技术指标计算预热期
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")

        print(f"📥 正在获取 {self.stock_code} 历史数据 ({start_date} ~ {end_date})...")
        df = self.fetcher.get_historical_kline(self.stock_code, start_date, end_date)

        if df is None or df.empty:
            return {"error": f"无法获取 {self.stock_code} 的历史数据"}

        print(f"✅ 获取到 {len(df)} 个交易日数据")

        # 计算技术指标（需要预热，我们多取了30天）
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_rsi(df)

        # 逐日模拟信号检测，并向前验证
        buy_signals = []   # (日期, 信号名, 信号强度, 当日收盘价, 是否有效)
        sell_signals = []

        # 从 MA20 和 MACD 需要的数据量之后开始（至少35行用于指标预热）
        warmup = 35
        if len(df) <= warmup:
            return {"error": "数据量不足，无法完成回测"}

        for i in range(warmup, len(df) - forward_days):
            # 截取到当天为止的数据（模拟实时场景）
            df_up_to_i = df.iloc[: i + 1].copy()

            # 检测信号（基于当天及之前的数据）
            signals = TechnicalAnalyzer.detect_signals(df_up_to_i)
            day = df.iloc[i]
            date_str = day["日期"]
            close_price = day["收盘"]

            # 向后看 forward_days 天的实际行情
            future = df.iloc[i + 1 : i + 1 + forward_days]
            future_low = future["最低"].min()
            future_high = future["最高"].max()

            for sig in signals:
                if sig["type"] == "buy":
                    # 买入建议验证：触发后N日内是否出现更低价格
                    # 如果出现了更低价格 → 建议偏早（not ideal）
                    # 如果没出现更低价格 → 建议时机好（good）
                    price_went_lower = future_low < close_price
                    buy_signals.append({
                        "date": date_str,
                        "signal": sig["signal"],
                        "strength": sig["strength"],
                        "price": close_price,
                        "future_low": future_low,
                        "future_low_pct": round((future_low - close_price) / close_price * 100, 2),
                        "effective": not price_went_lower,
                        "label": "✅ 好时机" if not price_went_lower else "❌ 偏早",
                    })

                elif sig["type"] == "sell":
                    # 卖出建议验证：触发后N日内是否出现更高价格
                    # 如果出现了更高价格 → 建议偏早（not ideal）
                    # 如果没出现更高价格 → 建议时机好（good）
                    price_went_higher = future_high > close_price
                    sell_signals.append({
                        "date": date_str,
                        "signal": sig["signal"],
                        "strength": sig["strength"],
                        "price": close_price,
                        "future_high": future_high,
                        "future_high_pct": round((future_high - close_price) / close_price * 100, 2),
                        "effective": not price_went_higher,
                        "label": "✅ 好时机" if not price_went_higher else "❌ 偏早",
                    })

        # 汇总统计
        result = {
            "stock_code": self.stock_code,
            "backtest_date": end_date,
            "data_days": len(df),
            "forward_days": forward_days,
            "buy_signals": {
                "total": len(buy_signals),
                "effective": sum(1 for s in buy_signals if s["effective"]),
                "accuracy": round(
                    sum(1 for s in buy_signals if s["effective"]) / len(buy_signals) * 100, 1
                ) if buy_signals else 0,
                "details": buy_signals,
            },
            "sell_signals": {
                "total": len(sell_signals),
                "effective": sum(1 for s in sell_signals if s["effective"]),
                "accuracy": round(
                    sum(1 for s in sell_signals if s["effective"]) / len(sell_signals) * 100, 1
                ) if sell_signals else 0,
                "details": sell_signals,
            },
        }

        # 综合准确率
        total_signals = len(buy_signals) + len(sell_signals)
        total_effective = (
            result["buy_signals"]["effective"] + result["sell_signals"]["effective"]
        )
        result["overall_accuracy"] = round(
            total_effective / total_signals * 100, 1
        ) if total_signals > 0 else 0

        # 分信号类型统计
        result["buy_by_signal"] = self._stats_by_signal_type(buy_signals)
        result["sell_by_signal"] = self._stats_by_signal_type(sell_signals)

        return result

    def _stats_by_signal_type(self, signals: List[Dict]) -> Dict:
        """按信号类型分组统计"""
        from collections import defaultdict
        groups = defaultdict(list)
        for s in signals:
            groups[s["signal"]].append(s)

        stats = {}
        for sig_name, items in groups.items():
            effective = sum(1 for s in items if s["effective"])
            stats[sig_name] = {
                "count": len(items),
                "effective": effective,
                "accuracy": round(effective / len(items) * 100, 1),
            }
        return stats

    @staticmethod
    def format_report(result: Dict) -> str:
        """生成可读的回测报告"""
        if "error" in result:
            return f"❌ 回测失败: {result['error']}"

        lines = [
            f"{'='*55}",
            f"🔬 做T信号回测报告",
            f"{'='*55}",
            f"📊 股票: {result['stock_code']}",
            f"📅 数据范围: {result['data_days']} 个交易日",
            f"⏩ 验证窗口: 信号触发后 {result['forward_days']} 个交易日",
            f"{'='*55}",
            "",
            f"📋 回测逻辑说明:",
            f"   🟢 买入信号 → 触发后 {result['forward_days']} 日内价格未再下跌 = ✅ 有效",
            f"   🔴 卖出信号 → 触发后 {result['forward_days']} 日内价格未再上涨 = ✅ 有效",
            "",
            f"🎯 综合准确率: {result['overall_accuracy']}%",
            f"{'─'*55}",
            "",
        ]

        # 买入信号统计
        bs = result["buy_signals"]
        lines.extend([
            f"🟢 买入信号回测:",
            f"   总触发次数: {bs['total']}",
            f"   有效次数: {bs['effective']} / {bs['total']}",
            f"   准确率: {bs['accuracy']}%",
        ])

        if result["buy_by_signal"]:
            lines.append("   分信号类型:")
            for sig, s in result["buy_by_signal"].items():
                bar = "█" * int(s["accuracy"] / 10) + "░" * (10 - int(s["accuracy"] / 10))
                lines.append(f"     {sig:20s} {s['accuracy']:5.1f}% {bar} ({s['effective']}/{s['count']})")

        lines.append("")

        # 卖出信号统计
        ss = result["sell_signals"]
        lines.extend([
            f"🔴 卖出信号回测:",
            f"   总触发次数: {ss['total']}",
            f"   有效次数: {ss['effective']} / {ss['total']}",
            f"   准确率: {ss['accuracy']}%",
        ])

        if result["sell_by_signal"]:
            lines.append("   分信号类型:")
            for sig, s in result["sell_by_signal"].items():
                bar = "█" * int(s["accuracy"] / 10) + "░" * (10 - int(s["accuracy"] / 10))
                lines.append(f"     {sig:20s} {s['accuracy']:5.1f}% {bar} ({s['effective']}/{s['count']})")

        # 综合评价
        lines.extend(["", f"{'─'*55}", "📝 综合评价:"])
        overall = result["overall_accuracy"]
        if overall >= 70:
            lines.append("   🌟 信号准确率较高，做T建议具有较高的参考价值")
        elif overall >= 50:
            lines.append("   💡 信号准确率中等，建议结合其他指标综合判断")
        elif overall > 0:
            lines.append("   ⚠️ 信号准确率偏低，建议谨慎参考，不宜单独依赖")
        else:
            lines.append("   ❓ 回测期内信号不足，无法得出有效结论")

        # 具体错失案例（展示最近的几个）
        buy_details = bs.get("details", [])
        sell_details = ss.get("details", [])

        if buy_details:
            lines.extend(["", f"{'─'*55}", "🟢 买入信号明细 (最近10条):"])
            lines.append(f"   {'日期':12s} {'信号':20s} {'价格':>8s} {'未来最低':>8s} {'偏移':>7s}  结果")
            for d in buy_details[-10:]:
                lines.append(
                    f"   {d['date']:12s} {d['signal']:20s} {d['price']:8.2f} {d['future_low']:8.2f} {d['future_low_pct']:+6.2f}%  {d['label']}"
                )

        if sell_details:
            lines.extend(["", f"{'─'*55}", "🔴 卖出信号明细 (最近10条):"])
            lines.append(f"   {'日期':12s} {'信号':20s} {'价格':>8s} {'未来最高':>8s} {'偏移':>7s}  结果")
            for d in sell_details[-10:]:
                lines.append(
                    f"   {d['date']:12s} {d['signal']:20s} {d['price']:8.2f} {d['future_high']:8.2f} {d['future_high_pct']:+6.2f}%  {d['label']}"
                )

        lines.extend([
            "",
            f"{'='*55}",
            "⚠️ 回测结果仅供参考，历史表现不代表未来收益。",
            f"{'='*55}",
        ])

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="A股做T信号回测工具 v1.3")
    parser.add_argument(
        "--stock", required=True, help="股票代码，如 sh600791"
    )
    parser.add_argument(
        "--days", type=int, default=60, help="回测历史天数 (默认60，实际拉取 days+30)"
    )
    parser.add_argument(
        "--forward", type=int, default=3, help="信号触发后向前看的天数 (默认3)"
    )
    parser.add_argument(
        "--json", action="store_true", help="输出 JSON 格式"
    )
    args = parser.parse_args()

    backtester = Backtester(args.stock)
    result = backtester.run(days=args.days, forward_days=args.forward)

    if args.json:
        # 输出 JSON（去掉明细列表以减小输出）
        json_result = {
            k: v for k, v in result.items()
            if k not in ("buy_signals", "sell_signals")
        }
        json_result["buy_signals"] = {
            k: v for k, v in result["buy_signals"].items()
            if k != "details"
        }
        json_result["sell_signals"] = {
            k: v for k, v in result["sell_signals"].items()
            if k != "details"
        }
        print(json.dumps(json_result, ensure_ascii=False, indent=2))
    else:
        print(Backtester.format_report(result))


if __name__ == "__main__":
    main()
