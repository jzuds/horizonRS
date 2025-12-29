# About the Grande Exchange (GE)
The Grand Exchange is a centralized, anonymous marketplace where buy and sell offers are matched by price and time priority, with prices shaped by real player supply and demand rather than a visible order book. For money-making, success comes from exploiting short-term inefficiencies in spread, volume, and fill speed while accounting for tax, liquidity, and execution risk.

## How do we define a flipping opportuntity?

> A flip is valid if it can be entered, exited quickly, and produces consistent profit after tax with acceptable fill probability.

$$
Expected Value = (Sell - Buy - Tax) \times FillRate > 0
$$

## How do we identify where the most profit is available at a given moment?

> We rank items by real-time net spread, trade volume, and fill speed to surface the highest profit opportunities right now.

$$
Opportunity Score = (Net Spread × Volume) / Estimated Time to Fill
$$

## How do we define risk profiles?

> Risk is based on how likely and how fast a trade can be exited without price slippage.

$$
Risk Score = Volatility / Volume Consistency
$$

## What is the information I need to execute these trades with confidence it is the correct trade?

> Only execution-critical data: buy price, sell price, net profit, volume, time to fill, and risk level.

## Data to consider for analysis
- Historic price history - [RuneScape:Real-time Prices](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices)
- Item stats / attributes / usage / drop tables - [osrsbox-api](https://github.com/0xNeffarion/osrsbox-api)
- [News](https://secure.runescape.com/m=news/archive?oldschool=1)