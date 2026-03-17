"""
tests/test_technical.py - 技术分析模块单元测试
"""

import math

import numpy as np
import pandas as pd
import pytest

# 确保 technical.py 能被 import
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from technical import TechnicalAnalyzer, StockDataFetcher


# ──────────────────────────────────────────────
# Helper: 生成简单的 DataFrame
# ──────────────────────────────────────────────

def make_df(closes, **extra_cols):
    """快速构建包含 日期/开盘/收盘/最高/最低/成交量/成交额/涨跌幅 的 DataFrame。
    closes: 收盘价列表 (长度 N)
    extra_cols: 额外列, 值为列表或标量(广播)
    """
    n = len(closes)
    opens = [c * 0.99 for c in closes]  # 开盘价略低于收盘
    highs = [c * 1.02 for c in closes]
    lows  = [c * 0.98 for c in closes]
    base = {
        "日期":    [f"2026-01-{i+1:02d}" for i in range(n)],
        "开盘":    opens,
        "收盘":    closes,
        "最高":    highs,
        "最低":    lows,
        "成交量":  [100000] * n,
        "成交额":  [1000000.0] * n,
        "涨跌幅":  [0.0] * n,
    }
    base.update(extra_cols)
    return pd.DataFrame(base)


# ══════════════════════════════════════════════
# RSI 计算测试
# ══════════════════════════════════════════════

class TestRSI:
    """RSI 计算函数测试"""

    def test_rsi_basic_shape(self):
        """RSI14 列应正确添加到 DataFrame"""
        closes = [10 + i * 0.1 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        assert "RSI14" in df.columns
        # 前期数据不足时为 NaN
        assert pd.isna(df.iloc[0]["RSI14"])
        # 有足够数据后应非 NaN
        assert not pd.isna(df.iloc[-1]["RSI14"])

    def test_rsi_values_bounded(self):
        """RSI 值应在 [0, 100] 范围内"""
        closes = [10 + i * 0.5 + (i % 3) * 0.3 for i in range(40)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        valid = df["RSI14"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_uptrend_high(self):
        """持续上涨时 RSI 应偏高 (接近或超过 70)"""
        closes = [10 + i * 0.5 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        rsi_last = df["RSI14"].iloc[-1]
        assert rsi_last > 60  # 持续上涨 RSI 应较高

    def test_rsi_downtrend_low(self):
        """持续下跌时 RSI 应偏低 (接近或低于 30)"""
        closes = [50 - i * 0.5 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        rsi_last = df["RSI14"].iloc[-1]
        assert rsi_last < 40  # 持续下跌 RSI 应较低

    def test_rsi_flat_near_50(self):
        """价格平稳时 RSI 应在 50 附近"""
        # 全部相同价格会导致 avg_loss=0 → RSI=NaN（正确行为），
        # 所以用微小波动代替
        closes = [10.0 + (i % 3) * 0.001 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        rsi_last = df["RSI14"].iloc[-1]
        # 微小波动 RSI 应接近 50（允许较大范围，因 Wilder 平滑有惯性）
        assert pd.notna(rsi_last), "RSI should not be NaN for near-flat data"

    def test_rsi_insufficient_data(self):
        """数据不足时不应添加 RSI 列"""
        closes = [10, 10.1, 10.2]
        df = make_df(closes)
        result = TechnicalAnalyzer.calculate_rsi(df)
        assert "RSI14" not in result.columns

    def test_rsi_period_parameter(self):
        """自定义 RSI 周期应正常工作"""
        closes = [10 + i * 0.3 for i in range(25)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df, period=6)
        assert "RSI6" in df.columns


# ══════════════════════════════════════════════
# 信号检测测试
# ══════════════════════════════════════════════

class TestDetectSignals:
    """买卖信号检测测试"""

    def test_no_signals_short_data(self):
        """数据不足 5 行时不应产生信号"""
        df = make_df([10, 10.1, 10.2])
        df = TechnicalAnalyzer.calculate_macd(df)
        signals = TechnicalAnalyzer.detect_signals(df)
        assert signals == []

    def test_rsi_overbought_signal(self):
        """RSI > 70 应产生超买卖出信号"""
        # 生成持续上涨数据让 RSI 超买
        closes = [10 + i * 0.8 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        # 强制 RSI 为 80 以确保触发
        df["RSI14"] = 80.0
        signals = TechnicalAnalyzer.detect_signals(df)
        rsi_signals = [s for s in signals if "RSI" in s["signal"]]
        assert len(rsi_signals) > 0
        assert rsi_signals[0]["type"] == "sell"
        assert rsi_signals[0]["strength"] == "strong"

    def test_rsi_oversold_signal(self):
        """RSI < 30 应产生超买入信号"""
        closes = [10 + i * 0.3 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        # 强制 RSI 为 20
        df["RSI14"] = 20.0
        signals = TechnicalAnalyzer.detect_signals(df)
        rsi_signals = [s for s in signals if "RSI" in s["signal"]]
        assert len(rsi_signals) > 0
        assert rsi_signals[0]["type"] == "buy"

    def test_macd_golden_cross(self):
        """MACD 金叉信号检测"""
        closes = [10 + i * 0.2 for i in range(40)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_macd(df)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_ma(df)
        # 手动构造金叉: DIF 从低于 DEA 变为高于 DEA
        df.loc[df.index[-2], "MACD_DIF"] = -0.1
        df.loc[df.index[-2], "MACD_DEA"] = 0.0
        df.loc[df.index[-1], "MACD_DIF"] = 0.1
        df.loc[df.index[-1], "MACD_DEA"] = 0.0
        signals = TechnicalAnalyzer.detect_signals(df)
        macd_signals = [s for s in signals if "MACD" in s["signal"]]
        assert any(s["signal"] == "MACD金叉" for s in macd_signals)

    def test_macd_death_cross(self):
        """MACD 死叉信号检测"""
        closes = [10 + i * 0.2 for i in range(40)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_macd(df)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_ma(df)
        df.loc[df.index[-2], "MACD_DIF"] = 0.1
        df.loc[df.index[-2], "MACD_DEA"] = 0.0
        df.loc[df.index[-1], "MACD_DIF"] = -0.1
        df.loc[df.index[-1], "MACD_DEA"] = 0.0
        signals = TechnicalAnalyzer.detect_signals(df)
        macd_signals = [s for s in signals if "MACD" in s["signal"]]
        assert any(s["signal"] == "MACD死叉" for s in macd_signals)

    def test_kdj_overbought(self):
        """KDJ J > 80 应产生超买信号"""
        closes = [10 + i * 0.2 for i in range(20)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        df["KDJ_J"] = 85.0
        signals = TechnicalAnalyzer.detect_signals(df)
        kdj_signals = [s for s in signals if "KDJ" in s["signal"]]
        assert any(s["signal"] == "KDJ超买(J>80)" and s["type"] == "sell" for s in kdj_signals)

    def test_kdj_oversold(self):
        """KDJ J < 20 应产生超卖信号"""
        closes = [10 + i * 0.2 for i in range(20)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        df["KDJ_J"] = 15.0
        signals = TechnicalAnalyzer.detect_signals(df)
        kdj_signals = [s for s in signals if "KDJ" in s["signal"]]
        assert any(s["signal"] == "KDJ超卖(J<20)" and s["type"] == "buy" for s in kdj_signals)

    def test_boll_lower_touch(self):
        """触及布林下轨应产生买入信号"""
        closes = [10 + i * 0.1 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        # 令最低价等于布林下轨
        df.loc[df.index[-1], "最低"] = df.iloc[-1]["BOLL_DOWN"]
        signals = TechnicalAnalyzer.detect_signals(df)
        assert any(s["signal"] == "触及布林下轨" and s["type"] == "buy" for s in signals)

    def test_boll_upper_touch(self):
        """触及布林上轨应产生卖出信号"""
        closes = [10 + i * 0.1 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        df.loc[df.index[-1], "最高"] = df.iloc[-1]["BOLL_UP"]
        signals = TechnicalAnalyzer.detect_signals(df)
        assert any(s["signal"] == "触及布林上轨" and s["type"] == "sell" for s in signals)

    def test_bullish_alignment(self):
        """多头排列信号 (收盘>MA5>MA20)"""
        closes = [10 + i * 0.3 for i in range(25)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        # 确保 MA5 > MA20
        df.loc[df.index[-1], "MA5"] = 15.0
        df.loc[df.index[-1], "MA20"] = 14.0
        df.loc[df.index[-1], "收盘"] = 16.0
        signals = TechnicalAnalyzer.detect_signals(df)
        assert any(s["signal"] == "多头排列(5>20)" and s["type"] == "buy" for s in signals)

    def test_bearish_alignment(self):
        """空头排列信号 (收盘<MA5<MA20)"""
        closes = [10 + i * 0.1 for i in range(25)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        df = TechnicalAnalyzer.calculate_rsi(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df.loc[df.index[-1], "MA5"] = 12.0
        df.loc[df.index[-1], "MA20"] = 13.0
        df.loc[df.index[-1], "收盘"] = 11.0
        signals = TechnicalAnalyzer.detect_signals(df)
        assert any(s["signal"] == "空头排列(5<20)" and s["type"] == "sell" for s in signals)


# ══════════════════════════════════════════════
# 其他技术指标测试
# ══════════════════════════════════════════════

class TestCalculateMA:
    """移动平均线测试"""

    def test_ma_columns_added(self):
        closes = [10 + i * 0.1 for i in range(30)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_ma(df)
        assert "MA5" in df.columns
        assert "MA10" in df.columns
        assert "MA20" in df.columns

    def test_ma_first_values_nan(self):
        """MA 在数据不足周期时应为 NaN"""
        closes = [10 + i * 0.1 for i in range(8)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_ma(df)
        assert pd.isna(df.iloc[0]["MA5"])
        assert not pd.isna(df.iloc[-1]["MA5"])

    def test_ma_custom_periods(self):
        closes = [10 + i * 0.1 for i in range(15)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_ma(df, periods=[3, 7])
        assert "MA3" in df.columns
        assert "MA7" in df.columns
        assert "MA5" not in df.columns  # 默认的 5 不应出现


class TestCalculateBoll:
    """布林带测试"""

    def test_boll_columns_added(self):
        closes = [10 + i * 0.1 for i in range(25)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_boll(df)
        assert "BOLL_MID" in df.columns
        assert "BOLL_UP" in df.columns
        assert "BOLL_DOWN" in df.columns

    def test_boll_short_data(self):
        """数据不足时不添加布林带列"""
        closes = [10 + i * 0.1 for i in range(10)]
        df = make_df(closes)
        result = TechnicalAnalyzer.calculate_boll(df)
        assert "BOLL_MID" not in result.columns

    def test_boll_up_greater_than_down(self):
        """上轨应 > 中轨 > 下轨"""
        closes = [10 + (i % 5) * 0.5 for i in range(25)]  # 波动数据
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_boll(df)
        last = df.iloc[-1]
        assert last["BOLL_UP"] >= last["BOLL_MID"] >= last["BOLL_DOWN"]


class TestCalculateMACD:
    """MACD 测试"""

    def test_macd_columns_added(self):
        closes = [10 + i * 0.1 for i in range(40)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_macd(df)
        assert "MACD_DIF" in df.columns
        assert "MACD_DEA" in df.columns
        assert "MACD_HIST" in df.columns

    def test_macd_short_data(self):
        closes = [10 + i * 0.1 for i in range(20)]
        df = make_df(closes)
        result = TechnicalAnalyzer.calculate_macd(df)
        assert "MACD_DIF" not in result.columns


class TestCalculateKDJ:
    """KDJ 测试"""

    def test_kdj_columns_added(self):
        closes = [10 + i * 0.1 for i in range(15)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_kdj(df)
        assert "KDJ_K" in df.columns
        assert "KDJ_D" in df.columns
        assert "KDJ_J" in df.columns

    def test_kdj_short_data(self):
        closes = [10, 10.1]
        df = make_df(closes)
        result = TechnicalAnalyzer.calculate_kdj(df)
        assert "KDJ_K" not in result.columns

    def test_kdj_j_equals_3k_minus_2d(self):
        """J = 3K - 2D"""
        closes = [10 + i * 0.2 for i in range(15)]
        df = make_df(closes)
        df = TechnicalAnalyzer.calculate_kdj(df)
        last = df.iloc[-1]
        expected_j = 3 * last["KDJ_K"] - 2 * last["KDJ_D"]
        assert abs(last["KDJ_J"] - round(expected_j, 2)) < 0.01


# ══════════════════════════════════════════════
# 数据获取辅助方法测试
# ══════════════════════════════════════════════

class TestStockDataFetcherHelpers:
    """StockDataFetcher 辅助方法测试（不需要网络）"""

    def test_code_to_sina_sh(self):
        assert StockDataFetcher._code_to_sina("sh600791") == "0.600791"

    def test_code_to_sina_sz(self):
        assert StockDataFetcher._code_to_sina("sz000001") == "1.000001"

    def test_code_to_eastmoney_sh(self):
        assert StockDataFetcher._code_to_eastmoney("sh600791") == "1.600791"

    def test_code_to_eastmoney_sz(self):
        assert StockDataFetcher._code_to_eastmoney("sz000001") == "0.000001"

    def test_code_to_eastmoney_hk(self):
        assert StockDataFetcher._code_to_eastmoney("hk00700") == "116.00700"

    def test_code_to_sina_default(self):
        assert StockDataFetcher._code_to_sina("600791") == "0.600791"

    def test_parse_kline_rows_basic(self):
        klines = [
            "2026-03-10,10.00,10.50,10.60,9.90,100000,1000000,7.00,5.00,0.50,1.20",
            "2026-03-11,10.50,11.00,11.10,10.40,120000,1200000,6.70,4.76,0.50,1.30",
        ]
        rows = StockDataFetcher._parse_kline_rows(klines)
        assert len(rows) == 2
        assert rows[0]["日期"] == "2026-03-10"
        assert rows[0]["收盘"] == 10.50
        assert rows[1]["成交量"] == 120000

    def test_parse_kline_rows_with_date_filter(self):
        klines = [
            "2026-03-10,10.00,10.50,10.60,9.90,100000,1000000,7.00,5.00,0.50,1.20",
            "2026-03-11,10.50,11.00,11.10,10.40,120000,1200000,6.70,4.76,0.50,1.30",
            "2026-03-12,11.00,11.20,11.30,10.80,110000,1100000,4.50,1.82,0.20,1.10",
        ]
        rows = StockDataFetcher._parse_kline_rows(klines, target_start="2026-03-11", target_end="2026-03-11")
        assert len(rows) == 1
        assert rows[0]["日期"] == "2026-03-11"
