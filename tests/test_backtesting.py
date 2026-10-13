import pandas as pd
from atlasynth.backtesting.engine import BacktestConfig, run_backtest
from conftest import make_candles


def test_signal_executes_no_earlier_than_next_open_and_costs_apply():
    candles = make_candles(8)
    signals = pd.DataFrame({"entry": [True, False, False, False, False, False, False, False],
                            "exit": [False, False, True, False, False, False, False, False],
                            "atr": [1.0] * 8})
    result = run_backtest(symbol="ETHUSDT", interval="1h", candles=candles, signals=signals,
                          strategy_id="unit", config=BacktestConfig(starting_cash=1000, fee_rate=0.001, slippage_bps=0))
    assert result.trades
    assert result.trades[0].entry_time_ms == candles[1].open_time_ms
    assert result.trades[0].exit_reason == "strategy_exit_next_open"
    assert result.live_trading_enabled is False
    assert len(result.equity_curve) == len(candles)


def test_backtest_worst_case_when_stop_and_target_both_touch():
    candles = make_candles(5)
    # Force a very wide second candle, touching both the 2x ATR stop and 2R target.
    c = candles[1]
    candles[1] = c.model_copy(update={"high": c.open + 10, "low": c.open - 10})
    signals = pd.DataFrame({"entry": [True, False, False, False, False], "exit": [False] * 5, "atr": [1.0] * 5})
    result = run_backtest(symbol="ETHUSDT", interval="1h", candles=candles, signals=signals,
                          strategy_id="unit", config=BacktestConfig(starting_cash=1000, slippage_bps=0))
    assert result.trades[0].exit_reason == "stop_loss"
