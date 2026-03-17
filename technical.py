#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股做T智能分析工具 - 数据获取模块
从新浪财经/东方财富获取实时行情和历史数据（自动容错切换）
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)


class StockDataFetcher:
    """股票数据获取器 - 免费 API"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # ---- 辅助方法 ----

    @staticmethod
    def _code_to_sina(stock_code: str) -> str:
        """将 stock_code 转换为新浪格式的代码（如 sh600791 -> 0.600791）"""
        if stock_code.startswith("sh"):
            return f"0.{stock_code[2:]}"
        elif stock_code.startswith("sz"):
            return f"1.{stock_code[2:]}"
        else:
            return f"0.{stock_code}"

    @staticmethod
    def _code_to_eastmoney(stock_code: str) -> str:
        """将 stock_code 转换为东方财富 secid（如 sh600791 -> 1.600791）"""
        if stock_code.startswith("sh"):
            return f"1.{stock_code[2:]}"
        elif stock_code.startswith("sz"):
            return f"0.{stock_code[2:]}"
        elif stock_code.startswith("hk"):
            return f"116.{stock_code[2:]}"
        else:
            return f"1.{stock_code}"

    @staticmethod
    def _get_realtime_quote_sina(stock_code: str) -> Optional[Dict]:
        """
        [Primary] 新浪财经实时行情（速度快、稳定）
        """
        try:
            code = StockDataFetcher._code_to_sina(stock_code)
            url = f"https://hq.sinajs.cn/list={code}"
            r = requests.get(url, headers=StockDataFetcher.HEADERS, timeout=10)

            # 新浪接口可能返回空数据（失效/停牌/网络问题）
            data_str = r.text.split('"')[1]
            parts = data_str.split(",")

            if len(parts) < 32:
                logger.warning("[Sina] 返回数据字段不足: %s", stock_code)
                return None

            return {
                "name": parts[0],
                "open": float(parts[1]),
                "yesterday_close": float(parts[2]),
                "current": float(parts[3]),
                "high": float(parts[4]),
                "low": float(parts[5]),
                "volume": int(parts[8]),
                "amount": float(parts[9]),
                "buy1_price": float(parts[6]),
                "sell1_price": float(parts[7]),
                "date": parts[30],
                "time": parts[31],
                "change_pct": round(
                    (float(parts[3]) - float(parts[2])) / float(parts[2]) * 100, 2
                ),
                "_source": "sina",
            }
        except IndexError:
            logger.warning("[Sina] 返回数据格式异常（可能接口变更）: %s", stock_code)
            return None
        except Exception as e:
            logger.warning("[Sina] 获取实时行情失败 %s: %s", stock_code, e)
            return None

    @staticmethod
    def _get_realtime_quote_eastmoney(stock_code: str) -> Optional[Dict]:
        """
        [Fallback] 东方财富实时行情（push2.eastmoney.com）
        当新浪接口返回 None 时自动调用
        """
        try:
            secid = StockDataFetcher._code_to_eastmoney(stock_code)
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170,f171",
            }
            r = requests.get(
                url, params=params, headers=StockDataFetcher.HEADERS, timeout=10
            )
            data = r.json()

            if not data.get("data") or data.get("rc") != 0:
                logger.warning("[EastMoney] 返回无效数据: %s", stock_code)
                return None

            d = data["data"]
            current = d.get("f43")
            if current is None or current == "-":
                logger.warning("[EastMoney] 当前价为空（可能停牌）: %s", stock_code)
                return None

            yesterday_close = d.get("f60") or 0
            change_pct = d.get("f169") or 0

            return {
                "name": d.get("f58", ""),
                "open": (d.get("f46") or 0) / 100,  # 东财价格单位为分
                "yesterday_close": yesterday_close / 100,
                "current": current / 100,
                "high": (d.get("f44") or 0) / 100,
                "low": (d.get("f45") or 0) / 100,
                "volume": d.get("f47") or 0,
                "amount": (d.get("f48") or 0),  # 东财成交额单位为元（整数）
                "buy1_price": 0,  # 东财单次查询不含买卖盘口，置0
                "sell1_price": 0,
                "date": str(d.get("f51", "")),
                "time": str(d.get("f52", "")),
                "change_pct": round(change_pct / 100, 2) if change_pct else 0,
                "_source": "eastmoney",
            }
        except Exception as e:
            logger.error("[EastMoney] 获取实时行情失败 %s: %s", stock_code, e)
            return None

    @staticmethod
    def get_realtime_quote(stock_code: str) -> Optional[Dict]:
        """
        获取A股实时行情（自动容错：新浪 -> 东方财富）
        返回 dict 中包含 '_source' 字段标识数据来源
        """
        # 优先使用新浪
        quote = StockDataFetcher._get_realtime_quote_sina(stock_code)
        if quote is not None:
            return quote

        logger.info("新浪接口失败，切换到东方财富: %s", stock_code)
        quote = StockDataFetcher._get_realtime_quote_eastmoney(stock_code)
        if quote is not None:
            return quote

        logger.error("所有数据源均失败: %s", stock_code)
        return None

    @staticmethod
    def _get_hk_realtime_quote_sina(stock_code: str) -> Optional[Dict]:
        """[Primary] 新浪港股实时行情"""
        try:
            code = stock_code.replace("hk", "").replace(".", "")
            url = f"https://hq.sinajs.cn/list=rt_hk{code}"
            r = requests.get(url, headers=StockDataFetcher.HEADERS, timeout=10)
            data_str = r.text.split('"')[1]
            parts = data_str.split(",")

            if len(parts) < 10:
                logger.warning("[Sina HK] 返回数据字段不足: %s", stock_code)
                return None

            return {
                "name": parts[1],
                "open": float(parts[2]),
                "yesterday_close": float(parts[3]),
                "high": float(parts[4]),
                "low": float(parts[5]),
                "current": float(parts[6]),
                "volume": int(parts[7]),
                "amount": float(parts[8]),
                "change_pct": round(
                    (float(parts[6]) - float(parts[3])) / float(parts[3]) * 100, 2
                ),
                "_source": "sina",
            }
        except Exception as e:
            logger.warning("[Sina HK] 获取港股行情失败 %s: %s", stock_code, e)
            return None

    @staticmethod
    def _get_hk_realtime_quote_eastmoney(stock_code: str) -> Optional[Dict]:
        """[Fallback] 东方财富港股实时行情"""
        try:
            secid = StockDataFetcher._code_to_eastmoney(stock_code)
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170",
            }
            r = requests.get(
                url, params=params, headers=StockDataFetcher.HEADERS, timeout=10
            )
            data = r.json()

            if not data.get("data") or data.get("rc") != 0:
                logger.warning("[EastMoney HK] 返回无效数据: %s", stock_code)
                return None

            d = data["data"]
            current = d.get("f43")
            if current is None or current == "-":
                return None

            yesterday_close = d.get("f60") or 0
            change_pct = d.get("f169") or 0

            return {
                "name": d.get("f58", ""),
                "open": (d.get("f46") or 0) / 100,
                "yesterday_close": yesterday_close / 100,
                "high": (d.get("f44") or 0) / 100,
                "low": (d.get("f45") or 0) / 100,
                "current": current / 100,
                "volume": d.get("f47") or 0,
                "amount": d.get("f48") or 0,
                "change_pct": round(change_pct / 100, 2) if change_pct else 0,
                "_source": "eastmoney",
            }
        except Exception as e:
            logger.error("[EastMoney HK] 获取港股行情失败 %s: %s", stock_code, e)
            return None

    @staticmethod
    def get_hk_realtime_quote(stock_code: str) -> Optional[Dict]:
        """
        获取港股实时行情（自动容错：新浪 -> 东方财富）
        """
        quote = StockDataFetcher._get_hk_realtime_quote_sina(stock_code)
        if quote is not None:
            return quote

        logger.info("新浪港股接口失败，切换到东方财富: %s", stock_code)
        quote = StockDataFetcher._get_hk_realtime_quote_eastmoney(stock_code)
        if quote is not None:
            return quote

        logger.error("所有港股数据源均失败: %s", stock_code)
        return None

    @staticmethod
    def _get_kline_eastmoney(stock_code: str, start_date: str, end_date: str, limit: int) -> Optional[List[str]]:
        """
        [Primary] 东方财富 K线数据 API
        返回原始 klines 列表（逗号分隔的字符串）
        """
        try:
            secid = StockDataFetcher._code_to_eastmoney(stock_code)

            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "1",
                "beg": start_date,
                "end": end_date,
                "lmt": str(limit),
            }

            r = requests.get(
                url, params=params, headers=StockDataFetcher.HEADERS, timeout=15
            )
            data = r.json()

            if data.get("rc") != 0 or not data.get("data"):
                logger.warning("[EastMoney Kline] 返回无效数据: %s", stock_code)
                return None

            return data["data"]["klines"]
        except Exception as e:
            logger.warning("[EastMoney Kline] 获取K线失败 %s: %s", stock_code, e)
            return None

    @staticmethod
    def _parse_kline_rows(klines: List[str], target_start: str = None, target_end: str = None) -> List[Dict]:
        """解析K线原始数据为标准 dict 列表"""
        rows = []
        for k in klines:
            parts = k.split(",")
            row_date = parts[0]
            if target_end and row_date > target_end:
                continue
            if target_start and row_date < target_start:
                continue
            rows.append(
                {
                    "日期": row_date,
                    "开盘": float(parts[1]),
                    "收盘": float(parts[2]),
                    "最高": float(parts[3]),
                    "最低": float(parts[4]),
                    "成交量": int(parts[5]),
                    "成交额": float(parts[6]),
                    "振幅": float(parts[7]),
                    "涨跌幅": float(parts[8]),
                    "涨跌额": float(parts[9]),
                    "换手率": float(parts[10]),
                }
            )
        return rows

    @staticmethod
    def get_daily_kline(stock_code: str, days: int = 30) -> Optional[pd.DataFrame]:
        """
        获取日K线数据（东方财富 API，免费）
        返回 DataFrame 包含: 日期,开盘,收盘,最高,最低,成交量,成交额
        """
        try:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

            klines = StockDataFetcher._get_kline_eastmoney(
                stock_code, start_date, end_date, days + 30
            )

            if klines is None:
                logger.error("[Kline] 获取K线数据失败: %s", stock_code)
                return None

            rows = StockDataFetcher._parse_kline_rows(klines)
            if not rows:
                return None

            df = pd.DataFrame(rows)
            return df.tail(days).reset_index(drop=True)
        except Exception as e:
            logger.error("[Kline] get_daily_kline 异常 %s: %s", stock_code, e)
            return None


    @staticmethod
    def get_historical_kline(
        stock_code: str,
        start_date: str,
        end_date: str = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取指定日期范围的日K线数据
        :param stock_code: 股票代码
        :param start_date: 开始日期 YYYY-MM-DD
        :param end_date: 结束日期 YYYY-MM-DD（默认今天）
        :return: DataFrame 包含: 日期,开盘,收盘,最高,最低,成交量,成交额,涨跌幅
        """
        try:
            if end_date is None:
                end_dt = datetime.now()
            else:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            # 多取30天缓冲，保证拿到足够的交易日数据
            buffer_start = (start_dt - timedelta(days=30)).strftime("%Y%m%d")
            end_date_str = end_dt.strftime("%Y%m%d")
            # 计算需要拉取的最大天数
            total_days = (end_dt - start_dt).days + 60

            klines = StockDataFetcher._get_kline_eastmoney(
                stock_code, buffer_start, end_date_str, total_days
            )

            if klines is None:
                logger.error("[Kline] get_historical_kline 失败: %s", stock_code)
                return None

            # 只保留目标范围内的数据
            rows = StockDataFetcher._parse_kline_rows(klines, start_date, end_date)

            if not rows:
                return None
            df = pd.DataFrame(rows)
            return df.reset_index(drop=True)
        except Exception as e:
            logger.error("[Kline] get_historical_kline 异常 %s: %s", stock_code, e)
            return None


class TechnicalAnalyzer:
    """技术分析模块"""

    @staticmethod
    def calculate_ma(df: pd.DataFrame, periods: List[int] = None) -> pd.DataFrame:
        """计算移动平均线"""
        if periods is None:
            periods = [5, 10, 20, 30, 60]
        for p in periods:
            if len(df) >= p:
                df[f"MA{p}"] = df["收盘"].rolling(p).mean().round(2)
        return df

    @staticmethod
    def calculate_boll(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """计算布林带"""
        if len(df) < period:
            return df
        df["BOLL_MID"] = df["收盘"].rolling(period).mean().round(2)
        std = df["收盘"].rolling(period).std()
        df["BOLL_UP"] = (df["BOLL_MID"] + 2 * std).round(2)
        df["BOLL_DOWN"] = (df["BOLL_MID"] - 2 * std).round(2)
        return df

    @staticmethod
    def calculate_macd(
        df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        """计算 MACD"""
        if len(df) < slow + signal:
            return df
        exp1 = df["收盘"].ewm(span=fast, adjust=False).mean()
        exp2 = df["收盘"].ewm(span=slow, adjust=False).mean()
        df["MACD_DIF"] = (exp1 - exp2).round(3)
        df["MACD_DEA"] = df["MACD_DIF"].ewm(span=signal, adjust=False).mean().round(3)
        df["MACD_HIST"] = (2 * (df["MACD_DIF"] - df["MACD_DEA"])).round(3)
        return df

    @staticmethod
    def calculate_kdj(df: pd.DataFrame, n: int = 9) -> pd.DataFrame:
        """计算 KDJ 指标"""
        if len(df) < n:
            return df
        low_list = df["最低"].rolling(n).min()
        high_list = df["最高"].rolling(n).max()
        rsv = (df["收盘"] - low_list) / (high_list - low_list) * 100

        df["KDJ_K"] = rsv.ewm(com=2, adjust=False).mean().round(2)
        df["KDJ_D"] = df["KDJ_K"].ewm(com=2, adjust=False).mean().round(2)
        df["KDJ_J"] = (3 * df["KDJ_K"] - 2 * df["KDJ_D"]).round(2)
        return df

    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算 RSI（相对强弱指数）"""
        if len(df) < period + 1:
            return df
        delta = df["收盘"].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        # Wilder's smoothing
        for i in range(period + 1, len(df)):
            avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period
        rs = avg_gain / avg_loss
        df[f"RSI{period}"] = (100 - 100 / (1 + rs)).round(2)
        return df

    @staticmethod
    def detect_signals(df: pd.DataFrame) -> List[Dict]:
        """检测买卖信号"""
        signals = []
        if len(df) < 5:
            return signals

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # 金叉信号
        if "MACD_DIF" in df.columns and "MACD_DEA" in df.columns:
            if (
                latest["MACD_DIF"] > latest["MACD_DEA"]
                and prev["MACD_DIF"] <= prev["MACD_DEA"]
            ):
                signals.append({"type": "buy", "signal": "MACD金叉", "strength": "medium"})
            elif (
                latest["MACD_DIF"] < latest["MACD_DEA"]
                and prev["MACD_DIF"] >= prev["MACD_DEA"]
            ):
                signals.append(
                    {"type": "sell", "signal": "MACD死叉", "strength": "medium"}
                )

        # KDJ 超买超卖
        if "KDJ_J" in df.columns:
            if latest["KDJ_J"] < 20:
                signals.append(
                    {"type": "buy", "signal": "KDJ超卖(J<20)", "strength": "strong"}
                )
            elif latest["KDJ_J"] > 80:
                signals.append(
                    {"type": "sell", "signal": "KDJ超买(J>80)", "strength": "strong"}
                )

        # 布林带信号
        if "BOLL_DOWN" in df.columns:
            if latest["最低"] <= latest["BOLL_DOWN"]:
                signals.append(
                    {"type": "buy", "signal": "触及布林下轨", "strength": "strong"}
                )
            if latest["最高"] >= latest["BOLL_UP"]:
                signals.append(
                    {"type": "sell", "signal": "触及布林上轨", "strength": "strong"}
                )

        # RSI 超买超卖
        if "RSI14" in df.columns:
            if latest["RSI14"] < 30:
                signals.append(
                    {"type": "buy", "signal": "RSI超卖(<30)", "strength": "strong"}
                )
            elif latest["RSI14"] > 70:
                signals.append(
                    {"type": "sell", "signal": "RSI超买(>70)", "strength": "strong"}
                )

        # 均线支撑/压力
        if "MA5" in df.columns and "MA20" in df.columns:
            if latest["收盘"] > latest["MA5"] > latest["MA20"]:
                signals.append({"type": "buy", "signal": "多头排列(5>20)", "strength": "weak"})
            elif latest["收盘"] < latest["MA5"] < latest["MA20"]:
                signals.append({"type": "sell", "signal": "空头排列(5<20)", "strength": "weak"})

        return signals


if __name__ == "__main__":
    # 配置日志（方便测试时看到容错切换）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    fetcher = StockDataFetcher()

    print("=== 测试 A股实时行情 ===")
    quote = fetcher.get_realtime_quote("sh600791")
    if quote:
        source = quote.pop("_source", "unknown")
        print(f"[数据源: {source}] {quote['name']} 当前: {quote['current']} 涨跌: {quote['change_pct']}%")
    else:
        print("A股实时行情获取失败（所有数据源均不可用）")

    print("\n=== 测试港股实时行情 ===")
    hk_quote = fetcher.get_hk_realtime_quote("hk00700")
    if hk_quote:
        source = hk_quote.pop("_source", "unknown")
        print(f"[数据源: {source}] {hk_quote['name']} 当前: {hk_quote['current']} 涨跌: {hk_quote['change_pct']}%")
    else:
        print("港股实时行情获取失败（所有数据源均不可用）")

    print("\n=== 测试日K线 ===")
    df = fetcher.get_daily_kline("sh600791", days=10)
    if df is not None:
        print(df.to_string())
    else:
        print("K线数据获取失败")

    print("\n=== 测试技术分析 ===")
    if df is not None:
        df = TechnicalAnalyzer.calculate_ma(df)
        df = TechnicalAnalyzer.calculate_boll(df)
        df = TechnicalAnalyzer.calculate_macd(df)
        df = TechnicalAnalyzer.calculate_kdj(df)
        signals = TechnicalAnalyzer.detect_signals(df)
        print(f"买卖信号: {json.dumps(signals, ensure_ascii=False)}")
        print(df[["日期", "收盘", "MA5", "MA10", "MACD_DIF", "MACD_DEA", "KDJ_J"]].to_string())
