"""
tests/test_analyzer.py - SmartTAnalyzer 单元测试
使用 mock 避免网络请求
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analyzer import SmartTAnalyzer


# ──────────────────────────────────────────────
# Helper: 生成 K线 DataFrame
# ──────────────────────────────────────────────

def make_kline_df(n=30, base_price=10.0, trend=0.1):
    """生成模拟 K线数据"""
    np.random.seed(42)
    closes = [base_price + i * trend + np.random.uniform(-0.3, 0.3) for i in range(n)]
    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
    return pd.DataFrame({
        "日期": dates,
        "开盘": [c * 0.99 for c in closes],
        "收盘": closes,
        "最高": [c * 1.02 for c in closes],
        "最低": [c * 0.98 for c in closes],
        "成交量": [int(100000 + np.random.uniform(-20000, 20000)) for _ in range(n)],
        "成交额": [1000000.0] * n,
        "涨跌幅": [np.random.uniform(-3, 3) for _ in range(n)],
    })


def make_quote():
    """生成模拟实时行情"""
    return {
        "name": "测试股票",
        "current": 12.50,
        "change_pct": 1.25,
        "open": 12.30,
        "high": 12.80,
        "low": 12.10,
        "_source": "mock",
    }


# ══════════════════════════════════════════════
# 分析流程测试
# ══════════════════════════════════════════════

class TestSmartTAnalyzer:
    """SmartTAnalyzer 核心测试"""

    @patch.object(SmartTAnalyzer, 'fetch_all')
    def test_analyze_returns_string(self, mock_fetch):
        """analyze() 应返回非空字符串"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        analyzer.df = df
        analyzer.quote = make_quote()
        mock_fetch.return_value = True

        result = analyzer.analyze()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "sh600791" in result.lower()

    @patch.object(SmartTAnalyzer, 'fetch_all')
    def test_analyze_contains_sections(self, mock_fetch):
        """分析报告应包含关键段落"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        analyzer.df = df
        analyzer.quote = make_quote()
        mock_fetch.return_value = True

        result = analyzer.analyze()
        assert "技术指标" in result
        assert "支撑位" in result
        assert "阻力位" in result
        assert "做T操作建议" in result
        assert "免责声明" in result

    @patch.object(SmartTAnalyzer, 'fetch_all')
    def test_analyze_with_rsi_info(self, mock_fetch):
        """报告应包含 RSI 信息"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        from technical import TechnicalAnalyzer
        df = TechnicalAnalyzer.calculate_rsi(df)
        analyzer.df = df
        analyzer.quote = make_quote()
        mock_fetch.return_value = True

        result = analyzer.analyze()
        assert "RSI" in result

    @patch.object(SmartTAnalyzer, 'fetch_all')
    def test_analyze_no_quote(self, mock_fetch):
        """无实时行情时也应正常分析"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        analyzer.df = df
        analyzer.quote = None
        mock_fetch.return_value = True

        result = analyzer.analyze()
        assert isinstance(result, str)
        assert "最新收盘" in result

    @patch.object(SmartTAnalyzer, 'fetch_all')
    def test_analyze_hk_stock(self, mock_fetch):
        """港股代码分析"""
        analyzer = SmartTAnalyzer("hk00700")
        df = make_kline_df(30, base_price=300)
        analyzer.df = df
        analyzer.quote = make_quote()
        mock_fetch.return_value = True

        result = analyzer.analyze()
        assert "HK" in result or "hk00700" in result.upper()


# ══════════════════════════════════════════════
# 风险检测测试
# ══════════════════════════════════════════════

class TestDetectRisks:
    """风险检测测试"""

    def test_no_data(self):
        """无数据时不应报风险"""
        analyzer = SmartTAnalyzer("sh600791")
        analyzer.df = None
        risks = analyzer._detect_risks()
        assert risks == []

    def test_insufficient_data(self):
        """数据不足 5 行时不应报风险"""
        analyzer = SmartTAnalyzer("sh600791")
        analyzer.df = make_kline_df(3)
        risks = analyzer._detect_risks()
        assert risks == []

    def test_consecutive_decline(self):
        """连续 5 日下跌应检测到风险"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(10, base_price=20, trend=-0.5)
        # 确保连续下跌
        for i in range(5, 10):
            df.loc[i, "收盘"] = df.loc[i - 1, "收盘"] - 0.5
        analyzer.df = df
        risks = analyzer._detect_risks()
        assert any("连续" in r and "下跌" in r for r in risks)

    def test_volume_spike(self):
        """成交量异常放大应检测到风险"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(10)
        # 正常量 100000 左右，最后一天放大到 10 倍
        df.loc[9, "成交量"] = 100000 * 10
        analyzer.df = df
        risks = analyzer._detect_risks()
        assert any("成交量异常" in r for r in risks)

    def test_below_ma20(self):
        """跌破 20 日均线应检测到风险"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(25)
        from technical import TechnicalAnalyzer
        df = TechnicalAnalyzer.calculate_ma(df)
        # 收盘价设为远低于 MA20
        if not pd.isna(df.iloc[-1]["MA20"]):
            df.loc[df.index[-1], "收盘"] = df.iloc[-1]["MA20"] * 0.9
        analyzer.df = df
        risks = analyzer._detect_risks()
        assert any("20日均线" in r for r in risks)

    def test_no_risk_normal_market(self):
        """正常市场不应报风险"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(10, base_price=10, trend=0.05)
        # 确保不是连续下跌（加一个上涨日）
        df.loc[9, "收盘"] = df.loc[8, "收盘"] + 0.3
        analyzer.df = df
        risks = analyzer._detect_risks()
        # 正常小幅波动不应有连续下跌或量能异常的风险
        assert not any("连续" in r or "异常" in r for r in risks)


# ══════════════════════════════════════════════
# to_dict() 输出测试
# ══════════════════════════════════════════════

class TestToDict:
    """to_dict() 结构化输出测试"""

    def test_no_data_returns_error(self):
        """无数据时返回 error"""
        analyzer = SmartTAnalyzer("sh600791")
        analyzer.df = None
        result = analyzer.to_dict()
        assert result == {"error": "no data"}

    def test_basic_keys_present(self):
        """应包含基本字段"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        analyzer.df = df
        analyzer.quote = make_quote()

        result = analyzer.to_dict()
        assert "stock" in result
        assert "name" in result
        assert "current" in result
        assert "change_pct" in result
        assert "timestamp" in result

    def test_quote_values_used(self):
        """有实时行情时应使用行情数据"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        analyzer.df = df
        analyzer.quote = make_quote()

        result = analyzer.to_dict()
        assert result["name"] == "测试股票"
        assert result["current"] == 12.50

    def test_fallback_to_kline_without_quote(self):
        """无实时行情时应使用 K线收盘价"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30, base_price=15.0)
        analyzer.df = df
        analyzer.quote = None

        result = analyzer.to_dict()
        assert result["name"] == "sh600791"  # 无 name 时用 code
        assert result["stock"] == "sh600791"

    def test_rsi_in_output(self):
        """RSI 数据应出现在 to_dict 输出中"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        from technical import TechnicalAnalyzer
        df = TechnicalAnalyzer.calculate_rsi(df)
        analyzer.df = df
        analyzer.quote = make_quote()

        result = analyzer.to_dict()
        assert "rsi14" in result
        assert "rsi_signal" in result
        assert result["rsi_signal"] in ("overbought", "oversold", "neutral")

    def test_rsi_overbought_signal(self):
        """RSI > 70 时 rsi_signal 应为 overbought"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        from technical import TechnicalAnalyzer
        df = TechnicalAnalyzer.calculate_rsi(df)
        # 手动设置 RSI
        df["RSI14"] = 75.0
        analyzer.df = df
        analyzer.quote = make_quote()

        result = analyzer.to_dict()
        assert result["rsi_signal"] == "overbought"

    def test_rsi_oversold_signal(self):
        """RSI < 30 时 rsi_signal 应为 oversold"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        from technical import TechnicalAnalyzer
        df = TechnicalAnalyzer.calculate_rsi(df)
        df["RSI14"] = 25.0
        analyzer.df = df
        analyzer.quote = make_quote()

        result = analyzer.to_dict()
        assert result["rsi_signal"] == "oversold"

    def test_timestamp_format(self):
        """timestamp 应为 ISO 格式"""
        analyzer = SmartTAnalyzer("sh600791")
        df = make_kline_df(30)
        analyzer.df = df
        analyzer.quote = make_quote()

        result = analyzer.to_dict()
        # ISO 格式应可被 datetime 解析
        parsed = datetime.fromisoformat(result["timestamp"])
        assert parsed is not None
