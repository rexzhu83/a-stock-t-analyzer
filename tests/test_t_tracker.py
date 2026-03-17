"""
tests/test_t_tracker.py - 做T收益追踪模块单元测试
使用临时目录避免污染项目数据
"""

import json
import os
import tempfile
from datetime import datetime

import pytest

import sys, os as _os
sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from t_tracker import TTracker


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def tracker(tmp_path):
    """每个测试用独立的临时目录"""
    return TTracker(data_dir=str(tmp_path))


@pytest.fixture
def populated_tracker(tmp_path):
    """预填充 3 条记录的 tracker"""
    t = TTracker(data_dir=str(tmp_path))
    t.add_record("sh600791", "2026-03-15", 16.20, 16.80, 16.15, 16.85, 16.65)
    t.add_record("sh600791", "2026-03-16", 16.00, 16.50, 16.10, 16.55, 16.40)
    t.add_record("sz000001", "2026-03-16", 12.00, 12.40, 11.90, 12.50, 12.30)
    return t


# ══════════════════════════════════════════════
# 记录添加测试
# ══════════════════════════════════════════════

class TestAddRecord:
    """add_record 测试"""

    def test_basic_record(self, tracker):
        """基本记录添加"""
        record = tracker.add_record("sh600791", "2026-03-17", 16.20, 16.80)
        assert len(tracker.records) == 1
        assert record["stock_code"] == "sh600791"
        assert record["date"] == "2026-03-17"
        assert record["buy_price"] == 16.20
        assert record["sell_price"] == 16.80

    def test_t_space_calculated(self, tracker):
        """做T空间自动计算"""
        record = tracker.add_record("sh600791", "2026-03-17", 16.20, 16.80)
        assert "t_space" in record
        assert record["t_space"] == 0.60
        assert "t_space_pct" in record
        # 0.60 / 16.20 * 100 ≈ 3.70%
        assert abs(record["t_space_pct"] - 3.70) < 0.1

    def test_validation_fields(self, tracker):
        """有实际价格时应计算验证字段"""
        record = tracker.add_record(
            "sh600791", "2026-03-17",
            buy_price=16.20, sell_price=16.80,
            actual_low=16.15, actual_high=16.85, actual_close=16.65
        )
        assert "buy_hit" in record
        assert "sell_hit" in record
        assert "perfect_t" in record

    def test_buy_hit_logic(self, tracker):
        """买入命中: 实际最低 <= 建议买入价 * 1.01"""
        record = tracker.add_record(
            "sh600791", "2026-03-17",
            buy_price=16.20, sell_price=16.80,
            actual_low=16.15, actual_high=16.85, actual_close=16.65
        )
        # 16.15 <= 16.20 * 1.01 = 16.362 → True
        assert record["buy_hit"] is True

    def test_buy_miss_logic(self, tracker):
        """买入未命中: 实际最低 > 建议买入价 * 1.01"""
        record = tracker.add_record(
            "sh600791", "2026-03-17",
            buy_price=16.20, sell_price=16.80,
            actual_low=17.00, actual_high=17.50, actual_close=17.20
        )
        # 17.00 > 16.20 * 1.01 = 16.362 → False
        assert record["buy_hit"] is False

    def test_sell_hit_logic(self, tracker):
        """卖出命中: 实际最高 >= 建议卖出价 * 0.99"""
        record = tracker.add_record(
            "sh600791", "2026-03-17",
            buy_price=16.20, sell_price=16.80,
            actual_low=16.15, actual_high=16.85, actual_close=16.65
        )
        # 16.85 >= 16.80 * 0.99 = 16.632 → True
        assert record["sell_hit"] is True

    def test_perfect_t(self, tracker):
        """双向命中 = 完美做T"""
        record = tracker.add_record(
            "sh600791", "2026-03-17",
            buy_price=16.20, sell_price=16.80,
            actual_low=16.15, actual_high=16.85, actual_close=16.65
        )
        assert record["perfect_t"] is True
        assert "max_profit_pct" in record
        assert "max_profit_per_10k" in record

    def test_perfect_t_profit(self, tracker):
        """完美做T收益计算"""
        record = tracker.add_record(
            "sh600791", "2026-03-17",
            buy_price=10.00, sell_price=11.00,
            actual_low=9.90, actual_high=11.10, actual_close=10.80
        )
        # (11 - 10) / 10 * 100 = 10%
        assert record["max_profit_pct"] == 10.0
        # (11 - 10) / 10 * 10000 = 1000
        assert record["max_profit_per_10k"] == 1000.0

    def test_no_validation_without_actual_prices(self, tracker):
        """无实际价格时不应有验证字段"""
        record = tracker.add_record("sh600791", "2026-03-17", 16.20, 16.80)
        assert "buy_hit" not in record
        assert "sell_hit" not in record

    def test_record_has_timestamp(self, tracker):
        """记录应包含时间戳"""
        record = tracker.add_record("sh600791", "2026-03-17", 16.20, 16.80)
        assert "timestamp" in record
        # 应可被解析为 ISO datetime
        datetime.fromisoformat(record["timestamp"])

    def test_persistence(self, tmp_path):
        """记录应持久化到磁盘"""
        t1 = TTracker(data_dir=str(tmp_path))
        t1.add_record("sh600791", "2026-03-17", 16.20, 16.80)

        # 新实例应能加载之前的记录
        t2 = TTracker(data_dir=str(tmp_path))
        assert len(t2.records) == 1
        assert t2.records[0]["stock_code"] == "sh600791"


# ══════════════════════════════════════════════
# 收益率 / 统计计算测试
# ══════════════════════════════════════════════

class TestGetStats:
    """get_stats 统计测试"""

    def test_empty_stats(self, tracker):
        """空记录统计"""
        stats = tracker.get_stats()
        assert stats["total_records"] == 0

    def test_total_records(self, populated_tracker):
        assert populated_tracker.get_stats()["total_records"] == 3

    def test_validated_records(self, populated_tracker):
        stats = populated_tracker.get_stats()
        assert stats["validated_records"] == 3  # 3 条都有 actual prices

    def test_buy_hit_rate(self, populated_tracker):
        stats = populated_tracker.get_stats()
        assert 0 <= stats["buy_hit_rate"] <= 100

    def test_sell_hit_rate(self, populated_tracker):
        stats = populated_tracker.get_stats()
        assert 0 <= stats["sell_hit_rate"] <= 100

    def test_avg_t_space_pct(self, populated_tracker):
        stats = populated_tracker.get_stats()
        assert stats["avg_t_space_pct"] > 0

    def test_filter_by_stock(self, populated_tracker):
        """按股票代码过滤"""
        stats = populated_tracker.get_stats(stock_code="sh600791")
        assert stats["total_records"] == 2

        stats_sz = populated_tracker.get_stats(stock_code="sz000001")
        assert stats_sz["total_records"] == 1

    def test_est_monthly_profit(self, populated_tracker):
        """月度收益估算"""
        stats = populated_tracker.get_stats()
        assert stats["est_monthly_profit_per_10k"] > 0

    def test_no_validation_records_stats(self, tracker):
        """无验证记录时比率应为 0"""
        tracker.add_record("sh600791", "2026-03-17", 16.20, 16.80)
        stats = tracker.get_stats()
        assert stats["buy_hit_rate"] == 0
        assert stats["sell_hit_rate"] == 0
        assert stats["perfect_t_rate"] == 0


# ══════════════════════════════════════════════
# 日期排序 / 记录顺序测试
# ══════════════════════════════════════════════

class TestRecordOrder:
    """记录顺序测试"""

    def test_records_appended_in_order(self, tracker):
        """记录按添加顺序排列"""
        tracker.add_record("sh600791", "2026-03-15", 16.20, 16.80)
        tracker.add_record("sh600791", "2026-03-16", 16.00, 16.50)
        tracker.add_record("sh600791", "2026-03-17", 16.10, 16.60)

        assert tracker.records[0]["date"] == "2026-03-15"
        assert tracker.records[1]["date"] == "2026-03-16"
        assert tracker.records[2]["date"] == "2026-03-17"

    def test_out_of_order_dates_preserved(self, tracker):
        """乱序添加日期应保持添加顺序"""
        tracker.add_record("sh600791", "2026-03-17", 16.10, 16.60)
        tracker.add_record("sh600791", "2026-03-15", 16.20, 16.80)
        tracker.add_record("sh600791", "2026-03-16", 16.00, 16.50)

        # 当前实现按添加顺序保存
        assert tracker.records[0]["date"] == "2026-03-17"
        assert tracker.records[1]["date"] == "2026-03-15"


# ══════════════════════════════════════════════
# 报告测试
# ══════════════════════════════════════════════

class TestReport:
    """报告生成测试"""

    def test_empty_report(self, tracker):
        report = tracker.get_report()
        assert "暂无做T记录" in report

    def test_populated_report(self, populated_tracker):
        report = populated_tracker.get_report()
        assert "做T收益追踪报告" in report
        assert "买入命中" in report
        assert "卖出命中" in report

    def test_multi_stock_report(self, populated_tracker):
        """多只股票时应显示分股统计"""
        report = populated_tracker.get_report()
        assert "分股统计" in report


# ══════════════════════════════════════════════
# CSV 导出测试
# ══════════════════════════════════════════════

class TestExportCSV:
    """CSV 导出测试"""

    def test_export_empty(self, tracker):
        result = tracker.export_csv()
        assert result is None

    def test_export_creates_file(self, populated_tracker, tmp_path):
        filepath = str(tmp_path / "test_export.csv")
        result = populated_tracker.export_csv(filepath=filepath)
        assert result == filepath
        assert os.path.exists(filepath)

        # 读取 CSV 验证内容
        with open(filepath, "r", encoding="utf-8-sig") as f:
            content = f.read()
        assert "sh600791" in content
        assert "sz000001" in content
