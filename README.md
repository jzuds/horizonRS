# HorizonRS

## Overview
Using numeric analysis to gain an edge in *Old School Runescape's* (OSRS) **Grand Exchange**.

## The problem
The OSRS Grand Exchange is a living, breathing ecosystem with fast-paced and dynamic trends. As a result, "merchers" have an excellent opportunity to financially capatilize on these evolving market conditions.

## Usage Input
- Users want to focus on short term flipping opportunities.
- Users want to select trade opportunities where we maximize profit and reduce risk.
- Users typically do not want to sift through alot of information and want a very "to the point" view of what should be executed on.
- Any downtime / increased latency on the streaming of information from this platform would be considered a potential profit loss and is generally considered undesirable by the user-base, this happening consistenly enough would causes users to start considering alternative platforms or services.

## Who is horizonRS for?

### The Active Flipper
**Short-Term, High-Frequency Trading**  
A player actively flips items during a session, relying on fast signals and quick fills to generate consistent profit.

### The Time-Constrained Mercher
**Maximum Profit With Minimal Playtime**  
A player with limited time uses HorizonRS to deploy capital efficiently without manual price checking.



### How do we define a flipping opportuntity?

> A flip is valid if it can be entered, exited quickly, and produces consistent profit after tax with acceptable fill probability.

$$
Expected Value = (Sell - Buy - Tax) \times FillRate > 0
$$

### How do we identify where the most profit is available at a given moment?

> We rank items by real-time net spread, trade volume, and fill speed to surface the highest profit opportunities right now.

$$
Opportunity Score = (Net Spread × Volume) / Estimated Time to Fill
$$

### How do we define risk profiles?

> Risk is based on how likely and how fast a trade can be exited without price slippage.

$$
Risk Score = Volatility / Volume Consistency
$$

### What is the information I need to execute these trades with confidence it is the correct trade?

> Only execution-critical data: buy price, sell price, net profit, volume, time to fill, and risk level.


## Factors to consider for analysis
- Historic price history - [RuneScape:Real-time Prices](https://oldschool.runescape.wiki/w/RuneScape:Real-time_Prices)
- Item stats / attributes / usage / drop tables - [osrsbox-api](https://github.com/0xNeffarion/osrsbox-api)
- [News](https://secure.runescape.com/m=news/archive?oldschool=1)

## Data sources to consider

## Contributing
- How to add new items or pipelines

## License
- See LICENSE file.
