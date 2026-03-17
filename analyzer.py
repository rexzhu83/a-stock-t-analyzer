#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股做T智能分析工具 - 主程序 v1.2
新增：RSI指标 + 做T收益追踪文档完善
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Dict, List

import pandas as pd
from technical import (
    StockDataFetcher,
    TechnicalAnalyzer,
)


class SmartTAnalyzer:
    """智能做T分析器 - 整合数据获取和技术分析"""

    def __init__(self, stock_code: str):
        self.stock_code = stock_code
        self.fetcher = StockDataFetcher()
        self.quote = None  # 实时行情
        self.df = None  # K线数据

    def fetch_all(self, days: int = 30) -> bool:
        """获取所有需要的数据"""
        # 获取实时行情
        if self.stock_code.startswith("hk"):
            self.quote = self.fetcher.get_hk_realtime_quote(self.stock_code)
        else:
            self.quote = self.fetcher.get_realtime_quote(self.stock_code)

        # 获取K线
        self.df = self.fetcher.get_daily_kline(self.stock_code, days=days)

        if self.df is None or self.df.empty:
            print(f"⚠️ 无法获取 {self.stock_code} 的K线数据")
            return False

        return True

    def analyze(self) -> str:
        """执行完整分析"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_weekday = datetime.now().strftime("%A")

        if not self.fetch_all(days=60):
            return f"⚠️ 无法分析 {self.stock_code}"

        # 技术分析
        self.df = TechnicalAnalyzer.calculate_ma(self.df)
        self.df = TechnicalAnalyzer.calculate_boll(self.df)
        self.df = TechnicalAnalyzer.calculate_macd(self.df)
        self.df = TechnicalAnalyzer.calculate_kdj(self.df)
        self.df = TechnicalAnalyzer.calculate_rsi(self.df)
        signals = TechnicalAnalyzer.detect_signals(self.df)

        latest = self.df.iloc[-1]
        prev = self.df.iloc[-2]
        recent_10 = self.df.tail(10)

        # 股票名称
        name = self.quote["name"] if self.quote else self.stock_code
        market = "HK" if self.stock_code.startswith("hk") else "A"

        # 量能分析
        vol_avg_10 = recent_10["成交量"].mean()
        vol_latest = latest["成交量"]
        vol_ratio = vol_latest / vol_avg_10 if vol_avg_10 > 0 else 1
        if vol_ratio > 1.5:
            vol_trend = f"放量 ↑ (量比{vol_ratio:.1f}x)"
        elif vol_ratio < 0.6:
            vol_trend = f"缩量 ↓ (量比{vol_ratio:.1f}x)"
        else:
            vol_trend = f"平量 → (量比{vol_ratio:.1f}x)"

        # 支撑位 / 阻力位
        supports = []
        resistances = []

        if "BOLL_DOWN" in self.df.columns and not pd.isna(latest["BOLL_DOWN"]):
            supports.append(("布林下轨", latest["BOLL_DOWN"]))
        if "BOLL_UP" in self.df.columns and not pd.isna(latest["BOLL_UP"]):
            resistances.append(("布林上轨", latest["BOLL_UP"]))
        if "MA20" in self.df.columns and not pd.isna(latest["MA20"]):
            supports.append(("20日均线", latest["MA20"]))
        if "MA10" in self.df.columns and not pd.isna(latest["MA10"]):
            supports.append(("10日均线", latest["MA10"]))
        resistances.append(("10日高点", recent_10["最高"].max()))
        supports.append(("10日低点", recent_10["最低"].min()))

        # 做T空间计算
        buy_price = supports[0][1] if supports else latest["收盘"] * 0.98
        sell_price = resistances[0][1] if resistances else latest["收盘"] * 1.02
        t_space_pct = (sell_price - buy_price) / buy_price * 100

        # === 输出 ===
        lines = [
            f"{'='*50}",
            f"📊 {name} ({self.stock_code.upper()}) 智能做T分析",
            f"📅 {today} {today_weekday}",
            f"{'='*50}",
            "",
            f"📌 行情速览:",
        ]

        if self.quote:
            lines.append(
                f"   当前: {self.quote['current']} | 涨跌: {self.quote['change_pct']:+.2f}%"
            )
            lines.append(
                f"   今开: {self.quote['open']} | 最高: {self.quote['high']} | 最低: {self.quote['low']}"
            )
        else:
            lines.append(
                f"   最新收盘: {latest['收盘']} | 涨跌: {latest['涨跌幅']:+.2f}%"
            )

        lines.extend(
            [
                "",
                f"📊 技术指标:",
                f"   MA5: {latest.get('MA5', 'N/A')} | MA10: {latest.get('MA10', 'N/A')} | MA20: {latest.get('MA20', 'N/A')}",
            ]
        )

        if "MACD_DIF" in self.df.columns:
            macd_signal = "金叉" if latest["MACD_DIF"] > latest["MACD_DEA"] else "死叉"
            lines.append(
                f"   MACD: DIF={latest['MACD_DIF']} DEA={latest['MACD_DEA']} ({macd_signal})"
            )

        if "KDJ_J" in self.df.columns:
            kdj_status = (
                "超买"
                if latest["KDJ_J"] > 80
                else ("超卖" if latest["KDJ_J"] < 20 else "中性")
            )
            lines.append(
                f"   KDJ: K={latest['KDJ_K']} D={latest['KDJ_D']} J={latest['KDJ_J']} ({kdj_status})"
            )

        if "BOLL_UP" in self.df.columns:
            boll_width = (
                (latest["BOLL_UP"] - latest["BOLL_DOWN"]) / latest["BOLL_MID"] * 100
                if latest["BOLL_MID"] > 0
                else 0
            )
            lines.append(
                f"   布林带: 上轨={latest['BOLL_UP']} 中轨={latest['BOLL_MID']} 下轨={latest['BOLL_DOWN']} (宽度{boll_width:.1f}%)"
            )

        if "RSI14" in self.df.columns:
            rsi_val = latest["RSI14"]
            if rsi_val > 70:
                rsi_status = "超买⚠️"
            elif rsi_val < 30:
                rsi_status = "超卖🟢"
            else:
                rsi_status = "中性"
            lines.append(f"   RSI(14): {rsi_val} ({rsi_status})")

        lines.extend(
            [
                "",
                f"📊 量能: {vol_trend} (10日均量{vol_avg_10:,.0f}股)",
                "",
                f"📍 支撑位:",
            ]
        )
        for n, p in supports:
            lines.append(f"   🟢 {n}: {p}")

        lines.append("📍 阻力位:")
        for n, p in resistances:
            lines.append(f"   🔴 {n}: {p}")

        # 做T建议
        lines.extend(
            [
                "",
                f"{'='*50}",
                f"💡 做T操作建议:",
                f"{'='*50}",
                f"   🟢 买入区间: {buy_price:.2f} - {buy_price * 1.01:.2f}",
                f"   🔴 卖出区间: {sell_price * 0.99:.2f} - {sell_price:.2f}",
                f"   📏 做T空间: {t_space_pct:.2f}%",
            ]
        )

        if t_space_pct < 1:
            lines.append("   ⚠️ 做T空间较小，建议观望或用半仓做微差")
        elif t_space_pct < 2:
            lines.append("   💡 做T空间适中，可正常操作")
        else:
            lines.append("   🔥 做T空间充足，可积极操作")

        # RSI 做T提示
        if "RSI14" in self.df.columns and not pd.isna(latest["RSI14"]):
            rsi_val = latest["RSI14"]
            if rsi_val > 70:
                lines.append("   📉 RSI超买区域，优先考虑卖出做T，暂缓买入")
            elif rsi_val < 30:
                lines.append("   📈 RSI超卖区域，优先考虑买入做T，暂缓卖出")

        # 买卖信号
        if signals:
            lines.extend(["", "📡 技术信号:"])
            buy_signals = [s for s in signals if s["type"] == "buy"]
            sell_signals = [s for s in signals if s["type"] == "sell"]

            if buy_signals:
                for s in buy_signals:
                    strength_emoji = {"strong": "🔥", "medium": "⚡", "weak": "·"}
                    lines.append(f"   🟢 {strength_emoji.get(s['strength'], '')} {s['signal']}")
            if sell_signals:
                for s in sell_signals:
                    strength_emoji = {"strong": "🔥", "medium": "⚡", "weak": "·"}
                    lines.append(f"   🔴 {strength_emoji.get(s['strength'], '')} {s['signal']}")

        # 风险提示
        risks = self._detect_risks()
        if risks:
            lines.extend(["", "⚠️ 风险提示:"])
            for risk in risks:
                lines.append(f"   {risk}")

        lines.extend(
            [
                "",
                f"{'='*50}",
                "⚠️ 免责声明：以上分析仅供参考，不构成投资建议。投资有风险，做T需谨慎。",
            ]
        )

        return "\n".join(lines)

    def _detect_risks(self) -> List[str]:
        """检测风险"""
        risks = []
        if self.df is None or len(self.df) < 5:
            return risks

        latest = self.df.iloc[-1]
        recent_5 = self.df.tail(5)

        # 连续下跌
        if all(
            recent_5.iloc[i]["收盘"] < recent_5.iloc[i - 1]["收盘"]
            for i in range(1, len(recent_5))
        ):
            risks.append("📉 连续5日下跌，注意止损")

        # 量能异常
        vol_avg = self.df["成交量"].mean()
        if latest["成交量"] > vol_avg * 2:
            risks.append("🔥 成交量异常放大（超均值2倍），注意方向选择")

        # 跌破均线
        if "MA20" in self.df.columns and not pd.isna(latest["MA20"]):
            if latest["收盘"] < latest["MA20"] * 0.95:
                risks.append("📉 跌破20日均线，趋势转弱")

        return risks

    def to_dict(self) -> Dict:
        """返回结构化数据（用于API/推送）"""
        if self.df is None:
            return {"error": "no data"}
        latest = self.df.iloc[-1]
        result = {
            "stock": self.stock_code,
            "name": self.quote["name"] if self.quote else self.stock_code,
            "current": self.quote["current"] if self.quote else latest["收盘"],
            "change_pct": (
                self.quote["change_pct"] if self.quote else latest["涨跌幅"]
            ),
            "timestamp": datetime.now().isoformat(),
        }
        # RSI
        if "RSI14" in self.df.columns and not pd.isna(latest["RSI14"]):
            result["rsi14"] = float(latest["RSI14"])
            if latest["RSI14"] > 70:
                result["rsi_signal"] = "overbought"
            elif latest["RSI14"] < 30:
                result["rsi_signal"] = "oversold"
            else:
                result["rsi_signal"] = "neutral"
        return result


def main():
    parser = argparse.ArgumentParser(description="A股做T智能分析工具 v1.2")
    parser.add_argument(
        "--stock", nargs="+", required=True, help="股票代码，如 sh600791 sh603268 hk06869"
    )
    parser.add_argument(
        "--days", type=int, default=60, help="K线数据天数 (默认60)"
    )
    parser.add_argument(
        "--json", action="store_true", help="输出 JSON 格式"
    )
    args = parser.parse_args()

    results = []
    for code in args.stock:
        analyzer = SmartTAnalyzer(code)
        results.append(analyzer.analyze())

    output = "\n\n".join(results)
    print(output)


if __name__ == "__main__":
    main()
