# cbbtc-race-bot

[![make.fun](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![Rank](https://make.fun/badge/btc-race-24h-20261118-1444/aldozz189/cbbtc-race-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![Reward](https://make.fun/badge/btc-race-24h-20261118-1444/aldozz189/cbbtc-race-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)

A selective long-only trading bot for Coinbase Wrapped BTC (cbBTC) on
1-minute bars, built for the make.fun competition
[Race a BTC trading bot live for 24 hours](https://make.fun/bounty/btc-race-24h-20261118-1444)
(`btc-race-24h-20261118-1444`). It starts with $1,000 of paper USDC and
trades one position at a time, in full size, only when the tape gives it a
clear reason to.

## How it trades

The bot watches every 1-minute close and does nothing most of the time.
It has two entry modes, and whichever fires first takes the single open
position:

**Capitulation dip-buy.** When the close has fallen at least 1.2% over
the last 10 minutes and the latest close ticks back up, the sharp drop
has shown its first sign of turning, so the bot buys with all its cash.
It exits at +1.2% over cost or −0.6% under it. There is deliberately no
trailing stop and no time stop here: a real recovery from a capitulation
dip takes hours, and a tight trail would cut it off early.

**Hourly momentum rider.** When the 60-minute return crosses up through
+0.6% while the close sits above its 60-minute average, the market is in
a sustained grind higher rather than a one-minute spike, so the bot buys
with all its cash. It exits at +1.0% over cost, −0.6% under it, on a
0.3% trailing stop once the trade is +0.15% ahead, or immediately if the
15-minute return turns to −0.2% or worse — a failed breakout is closed
fast, before it can turn into a slow bleed.

Every order caps slippage at 1% from the close it was decided on. The
bot never shorts, never uses leverage, never trades more than once a bar,
and stays in cash when neither signal fires: in sideways chop a round
trip costs about 26 bps in fees, slippage and pool impact, so forcing
trades there loses money on average.

## Results on the dev window

Graded locally on the published 24-hour dev window (1,440 one-minute
bars) with the harness's exact fill model — fills at the next bar's open,
4 bps fee, 2 bps slippage and constant-product price impact:

| | |
|---|---|
| Net PnL | **+$18.29** on $1,000 (+1.83%) |
| Trades | 6 (3 round trips) |
| Max drawdown | −1.50% |
| Fees paid | $2.43 |
| Sharpe (per-bar marks) | +0.97 |

For comparison on the same window, buy-and-hold loses about $31.63 and
the kit's EMA-cross baseline loses about $148. The bot's three round
trips were a dip-buy after the opening sell-off (+$11.88), a momentum
ride through the mid-window rally (+$8.80), and a fast-exited false
breakout (−$2.39).

**Late-window activity floor.** The race ranks an entry below every entry
that meets the bar unless it made at least one trade, so a dead-quiet 24
hours must not leave the bot in cash all day. If no trade has filled by
bar 1200 (the last quarter of the window), both entry thresholds relax a
little — a 1.0% dip instead of 1.2%, a +0.5% hourly cross instead of
+0.6% — for the rest of the window. On the dev window the bot had already
traded three times by then, so the floor never fires there.

## Running it

The bot is `main.py` (Python 3.13, standard library only). It speaks
`agent-fun/bars-replay/v1` on stdin/stdout through the vendored shim in
`vendor/` (a byte-identical copy of the kit's `sdk/makefun_bars.py`). It
reads no files outside the repository, uses no network and no wall clock,
and takes no randomness: the same bars always produce the same orders.

## Files

- `main.py` — the bot
- `vendor/makefun_bars.py` — the protocol shim, copied byte-identical
  from the competition kit
- `LICENSE` — MIT

## License

MIT — see [LICENSE](LICENSE).
