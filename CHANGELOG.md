# Changelog

All notable changes to the A股做T智能分析工具 project.

## [Unreleased]

### Added
- **单元测试框架**: 添加 pytest 配置和 83 个单元测试用例
  - `tests/test_technical.py`: RSI 计算、信号检测（超买/超卖/金叉/死叉/布林带/均线排列）、MA/布林带/MACD/KDJ 指标计算、数据源辅助方法
  - `tests/test_analyzer.py`: 分析流程（mock 数据）、风险检测（连续下跌/量能异常/跌破均线）、to_dict() 结构化输出格式
  - `tests/test_t_tracker.py`: 记录添加、做T空间计算、买入/卖出命中逻辑、完美做T收益、统计过滤、日期排序、CSV 导出、持久化

## [1.3.0] - 2026-03-17

### Added
- **东方财富实时行情备用数据源**: 新浪财经接口失败时自动切换到东方财富 push2 API
- **港股备用数据源**: 港股行情同样支持新浪 -> 东方财富双数据源容错
- **数据来源标识**: 实时行情返回数据中新增 `_source` 字段（sina/eastmoney）
- **完整日志系统**: 添加 logging 日志，记录数据源切换、失败原因等

### Changed
- 重构代码转换逻辑：提取 `_code_to_sina()` / `_code_to_eastmoney()` 辅助方法
- 重构 K 线获取逻辑：提取 `_get_kline_eastmoney()` / `_parse_kline_rows()` 公共方法
- 增强错误处理：区分 IndexError（接口变更）和其他异常

## [1.2.0] - 2026-03-17

### Added
- **RSI 指标**: 新增 RSI（相对强弱指数）计算，默认14日周期，使用 Wilder 平滑法
- **RSI 信号检测**: RSI>70 超买信号、RSI<30 超卖信号，自动纳入买卖信号列表
- **RSI 做T建议**: 分析报告中显示 RSI 数值与状态，超买时优先卖出、超卖时优先买入
- **RSI 结构化输出**: `to_dict()` 返回 `rsi14` 数值和 `rsi_signal`（overbought/oversold/neutral）
- **README 补充**: 新增 `t_tracker.py`（做T收益追踪）功能文档和使用示例

### Changed
- 版本号 v1.1 → v1.2

## [1.1.0] - 2026-03-17

### Added
- **MACD/KDJ/布林带技术指标**: 全套技术分析
- **实时行情**: 新浪/东方财富免费 API
- **买卖信号检测**: 金叉死叉、超买超卖、多头空头排列
- **港股支持**: 同时支持沪深和港股

### Fixed
- K线数据获取容错处理
- 做T空间计算精度修正
