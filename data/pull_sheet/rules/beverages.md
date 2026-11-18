# Beverage pull sheet rules

How to work out the beverage section of a pull sheet from a BEO: how many gallons of each drink, which cambros, how many cups and which other supplies. This page mirrors `data/pull_sheet/rules/beverages.json`, which the pull sheet program uses. Keep the two in sync when the rules change. For exact numbers on a real event, run the pull sheet program on the BEO.

## How many gallons to make
The rule is 1 gallon per 25 guests, rounded to the nearest whole gallon (exactly half rounds up), with a minimum of 1 gallon. Work out each drink separately. If a BEO line gives the amount in gallons (Delivery UOM "Gallon"), use that number of gallons directly.
- 1 to 37 guests: make 1 gallon of each drink.
- 38 to 62 guests: make 2 gallons of each drink.
- 63 to 87 guests: make 3 gallons of each drink.
- 88 to 112 guests: make 4 gallons of each drink.
- 113 to 137 guests: make 5 gallons of each drink.
- 138 to 162 guests: make 6 gallons of each drink.
- 163 to 187 guests: make 7 gallons of each drink.
- 188 to 212 guests: make 8 gallons of each drink.
- Example: 50 guests need 2 gallons of coffee.
- Example: 70 guests need 3 gallons of coffee.
- Example: 100 guests need 4 gallons of coffee.
- Example: 150 guests need 6 gallons of iced water.

## Cambros
We have three cambro sizes: 5 gal, 2 gal and 1 gal. Each drink gets its own cambros; two drinks never share a cambro. For one drink, take a 5 gal cambro for every full 5 gallons. If any gallons are left, take one cambro of the smallest size that holds the rest, so 3 or 4 leftover gallons go in one 5 gal cambro, not a 2 gal plus a 1 gal.
- 1 gallon of one drink: bring one 1 gal cambro.
- 2 gallons of one drink: bring one 2 gal cambro.
- 3 gallons of one drink: bring one 5 gal cambro.
- 4 gallons of one drink: bring one 5 gal cambro.
- 5 gallons of one drink: bring one 5 gal cambro.
- 6 gallons of one drink: bring one 5 gal cambro and one 1 gal cambro.
- 7 gallons of one drink: bring one 5 gal cambro and one 2 gal cambro.
- 8 gallons of one drink: bring two 5 gal cambros.
- 9 gallons of one drink: bring two 5 gal cambros.
- 10 gallons of one drink: bring two 5 gal cambros.
- 11 gallons of one drink: bring two 5 gal cambros and one 1 gal cambro.
- 12 gallons of one drink: bring two 5 gal cambros and one 2 gal cambro.
- Example: 7 gallons of coffee need one 5 gal cambro and one 2 gal cambro.
- Example: 3 gallons of coffee and 3 gallons of decaf need two 5 gal cambros, one for each drink.

## Cups
Bring hot cups when any hot drink is ordered: coffee, decaf, hot water (tea), brewed hot cider or Ginger Honeycrisp apple cider. Bring cold cups when any cold drink is ordered: iced water, iced tea, orange juice, lemonade or peach tea. The number of cups is guests + extras. One set of hot cups covers all hot drinks, and one set of cold cups covers all cold drinks. Guests here means the larger of the BEO's Guest Count and the guest quantity on any beverage line.
- Up to 20 guests: add 10 extra cups.
- 21 to 50 guests: add 20 extra cups.
- 51 to 100 guests: add 50 extra cups.
- More than 100 guests: add 100 extra cups.
- Example: 20 guests need 30 cups.
- Example: 50 guests need 70 cups.
- Example: 70 guests need 120 cups.
- Example: 100 guests need 150 cups.
- Example: 150 guests need 250 cups.

## Other supplies
- Cocktail napkins: bring them (no count) when any beverage is ordered.
- Creamer: bring it (no count) when coffee or decaf is ordered.
- Stir sticks: bring 1 per event when coffee, decaf or hot water (tea) is ordered.
- Sugar: bring 1 per event when coffee, decaf or hot water (tea) is ordered.
- Lemon tongs: bring 1 per event when hot water (tea) is ordered.
- Lemons: bring them (no count) when hot water (tea) or iced tea is ordered.
- Tea packets: bring 1 per event when hot water (tea) is ordered.

Pull once, don't add up: if several drinks need the same supply, bring it once. Example: coffee and hot water both need sugar, so bring 1 sugar, not 2.

## Example pull sheet
BEO: Guest Count 70, with the line "Coffee, decaf, tea, iced water & juice" for 70 guests. That is 3 gallons each of coffee, decaf, hot water, iced water and orange juice. The pull sheet is:
- 5 gal cambro: 5 (one per drink)
- hot-cups: 120
- cold-cups: 120
- Cocktail napkins: bring
- Creamer: bring
- Stir sticks: 1
- Sugar: 1
- Lemon tongs: 1
- Lemons: bring
- Tea packets: 1
