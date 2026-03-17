#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例：一键生成多只股票做T分析报告
"""

from datetime import datetime

from analyzer import SmartTAnalyzer

# 持仓股票配置
PORTFOLIO = {
    "sh600791": {"name": "京能置业", "shares": 10000, "style": "做T"},
    "sh603268": {"name": "松发股份", "shares": 400, "cost": 127.328, "style": "做T"},
    "hk06869": {"name": "长飞光纤光缆", "market_value": 51000000, "cost": 40, "style": "做T"},
}


def generate_daily_report():
    """生成每日做T分析报告"""
    for code, info in PORTFOLIO.items():
        print(f"\n正在分析 {info['name']} ({code})...")
        analyzer = SmartTAnalyzer(code)
        try:
            report = analyzer.analyze()
            print(report)

            # 保存到文件
            filename = f"reports/{code}_{datetime.now().strftime('%Y-%m-%d')}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(report)
        except Exception as e:
            print(f"分析失败: {e}")


if __name__ == "__main__":
    generate_daily_report()
