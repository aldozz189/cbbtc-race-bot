"""cbBTC race bot: selective long-only trader for agent-fun/bars-replay/v1.

Strategy (two entry modes, one position at a time, full-size entries):

1. Capitulation dip-buy.  Bitcoin's 1-minute tape mean-reverts after sharp
   air pockets: when the close has fallen at least 1.2% over the last 10
   minutes and the latest close ticks back up, buy with all cash.  The dip
   has to prove itself with an up-close first, so the bot never catches a
   knife while it is still falling.  Exit at +1.2% over cost or -0.6% under
   it; no trailing stop and no time stop, because a real capitulation
   recovery takes hours to play out and a tight trail cuts it short.

2. Hourly momentum rider.  When the 60-minute return crosses up through
   +0.6% while the close sits above its 60-minute average, the tape is in a
   sustained grind higher rather than a one-minute spike, so buy with all
   cash.  Exit at +1.0% over cost, -0.6% under it, on a 0.3% trailing stop
   once the trade is +0.15% ahead, or at once if the 15-minute return turns
   to -0.2% or worse (a failed breakout is exited fast, before it becomes
   a slow bleed).

Everything else the bot does is defensive: it stays in cash when neither
signal fires (cash earns nothing, but a forced trade in chop pays ~26 bps
a round trip in fee, slippage and pool impact and loses money on average);
it never trades more than once per bar, never holds more than one
position, and every order caps slippage at 1% from the close it was
decided on.  All decisions use only closes the bot has already been sent,
so the bot is deterministic: same bars, same orders, every run.

One last guardrail: the race ranks an entry below every entry that meets
the bar unless it made at least 1 trade, so a dead-quiet 24 hours must
not leave the bot in cash all day.  If no trade has filled by bar 1200
(the last quarter of the window), both entry thresholds relax a little
(a 1.0% dip instead of 1.2%, a +0.5% hourly cross instead of +0.6%) for
the rest of the window.  On the dev window the bot had already traded
three times by then, so the floor never fires there and changes nothing;
it only buys the bot a chance at the 1-trade bar on a quiet race day.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
MAX_SLIPPAGE_BPS = 100  # 1% from the close the order was decided on

# Capitulation dip-buy.
CAP_DROP_BARS = 10       # drop measured over this many minutes
CAP_DROP = 0.012         # ... of at least 1.2%
CAP_TAKE_PROFIT = 0.012  # exit +1.2% over cost
# Momentum rider.
MOM_LOOKBACK_BARS = 60   # 60-minute return
MOM_CROSS = 0.006        # ... crossing up through +0.6%
MOM_SMA_BARS = 60        # close must sit above this average
MOM_TAKE_PROFIT = 0.010  # exit +1.0% over cost
MOM_TRAIL = 0.003        # trailing stop, 0.3% off the peak since entry
MOM_TRAIL_ARM = 0.0015   # ... armed only once +0.15% ahead
MOM_FAST_EXIT = -0.002   # exit at once if the 15-minute return hits -0.2%
STOP_LOSS = 0.006        # hard stop for both modes: -0.6% under cost

# Late-window activity floor: if nothing has traded by this bar, relax
# both entry thresholds a little so a quiet window still sees a trade.
FLOOR_BAR = 1200         # last quarter of the 1,440-bar window
FLOOR_CAP_DROP = 0.010   # ... a 1.0% dip instead of 1.2%
FLOOR_MOM_CROSS = 0.005  # ... a +0.5% hourly cross instead of +0.6%

# Closes by batch seq (the bar's close time is seq-indexed, so a missing
# bar leaves a hole instead of shifting every lookback by one).
closes = {}
# Which mode the open position (or the buy just decided) belongs to.
mode = None
# Seq of the bar whose open filled the open position, and the highest close
# seen since then (for the momentum trailing stop).
entry_seq = None
peak_close = None
# Filled buys so far (the late-window floor only fires if this is still 0).
trades_taken = 0


def close_at(seq):
    return closes.get(seq)


def ret_bars(seq, bars):
    """Close-to-close return over `bars` minutes ending at `seq`, or None."""
    now = close_at(seq)
    then = close_at(seq - bars)
    if now is None or then is None or then == 0:
        return None
    return now / then - 1.0


def sma_bars(seq, bars):
    """Mean of the last `bars` closes ending at `seq`, or None."""
    total = 0.0
    for s in range(seq - bars + 1, seq + 1):
        c = close_at(s)
        if c is None:
            return None
        total += c
    return total / bars


def on_batch(state, batch):
    global mode, entry_seq, peak_close, trades_taken
    bar = state.latest.get(SYMBOL)
    if bar is not None:
        closes[state.seq] = int(bar["c"])
    held = state.positions.get(SYMBOL)
    close = state.close(SYMBOL)

    # A buy decided on the previous batch has now filled: the batch's fills
    # tell us, and the fill bar is this batch's seq.
    for fill in batch.get("fills", []):
        if fill.get("symbol") == SYMBOL and fill.get("side") == "buy" \
                and fill.get("status") == "filled":
            entry_seq = state.seq
            peak_close = close
            trades_taken += 1
    if held is not None and close is not None:
        if peak_close is None or close > peak_close:
            peak_close = close

    if state.warming_up or close is None:
        return []

    if held is not None:
        value = state.value(SYMBOL, held.qty)
        ret = value / held.cost - 1.0 if held.cost else 0.0
        if mode == "cap":
            if ret >= CAP_TAKE_PROFIT or ret <= -STOP_LOSS:
                mode = None
                entry_seq = None
                peak_close = None
                return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            return []
        # Momentum mode.
        if ret >= MOM_TAKE_PROFIT or ret <= -STOP_LOSS:
            mode = None
            entry_seq = None
            peak_close = None
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        r15 = ret_bars(state.seq, 15)
        if r15 is not None and r15 <= MOM_FAST_EXIT:
            mode = None
            entry_seq = None
            peak_close = None
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        if peak_close is not None and ret > MOM_TRAIL_ARM \
                and close <= peak_close * (1.0 - MOM_TRAIL):
            mode = None
            entry_seq = None
            peak_close = None
            return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # Flat: look for an entry.  Capitulation first: a sharp 10-minute drop
    # that has just ticked back up.
    prev = close_at(state.seq - 1)
    r10 = ret_bars(state.seq, CAP_DROP_BARS)
    # Late-window floor: with no trade yet by FLOOR_BAR, accept a
    # slightly shallower dip and a slightly lower hourly cross.
    floor = state.seq >= FLOOR_BAR and trades_taken == 0
    cap_drop = FLOOR_CAP_DROP if floor else CAP_DROP
    mom_cross = FLOOR_MOM_CROSS if floor else MOM_CROSS
    if r10 is not None and r10 <= -cap_drop and prev is not None and close > prev:
        if state.cash >= int(state.hello["fees"]["min_notional_quote_units"]):
            mode = "cap"
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]

    # Momentum: the 60-minute return crossing up through +0.6% with the
    # close above its 60-minute average.
    r60 = ret_bars(state.seq, MOM_LOOKBACK_BARS)
    r60_prev = ret_bars(state.seq - 1, MOM_LOOKBACK_BARS)
    sma60 = sma_bars(state.seq, MOM_SMA_BARS)
    if r60 is not None and r60_prev is not None and sma60 is not None \
            and r60 >= mom_cross and r60_prev < mom_cross and close > sma60:
        if state.cash >= int(state.hello["fees"]["min_notional_quote_units"]):
            mode = "mom"
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]

    return []


makefun_bars.run(on_batch)
