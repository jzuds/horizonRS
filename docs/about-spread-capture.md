# Spread Captures
> Ride very short-lived directional movement. The market is not mispriced — it is temporarily inefficient due to impatience, anonymity, and tax friction.

- **Signal:** Buy–sell spread > tax + buffer
- **Risk:** Low 
- **Time Horizon:** Minutes → hours
- **Capital:** Scales extremely well 
- **Failure Mode:** Slow fills or spread compression
- **Why it works:** GE’s hidden order book + impatient players constantly create exploitable spreads, especially on high-volume consumables.
- **Target Items:** Runes, food, potions, darts, common PvM supplies

### Spread Capture Signals
**A. Net Spread After Tax - Authoritative**
- Spread must exceed GE tax + safety buffer
- Buffer absorbs minor price movement and rounding
- This is a hard gate, not a ranking signal.

**B. Liquidity (Volume) - Authoritative**
> Spread without volume is unusable.
- High trade frequency ensures fast entry and exit
- Consistent volume reduces tail risk

**C. Fill Speed Symmetry - Inferred**
> Both sides must fill quickly.
- Buy fill time is predictable
- Sell fill time is predictable
- Neither side dominates (neutral market), this distinguishes spread captures from momentum trades.

**D. Spread Stability - Derived**
> You want persistent spreads, not flickering ones.
- Spread remains open across multiple price updates
- No rapid compression during observation window
- Stable spreads imply structural inefficiency, not noise.

**E. Competition Pressure - Indirect Proxy**
> Some spreads look good but are overcrowded.
- Frequent 1–2 gp undercuts
- Rapid spread collapse after entry
- Lower competition = higher realized EV.
