"""Record current bev/recipe calculation results as a characterization snapshot (spec 024)."""
import json, sys
from fractions import Fraction
from itertools import product
sys.path.insert(0, "src")
from blc.tools.bev_tools import BEV_ITEMS, DrinkRequest, calculate_bev_item
from blc.tools.recipe_tools import load_recipe_book, run_recipe_tool

def frac(x):
    return None if x is None else str(x)

GUESTS = [None, 1, 20, 21, 50, 51, 100, 101, 400]
AMOUNTS = [None, 1, 2.5, 3, 7, 12]
SINGLE = ["Coffee", "Decaf", "Hot water", "Brewed hot cider", "Ginger Honeycrisp apple cider",
          "Iced water", "Iced tea", "Orange juice", "Lemonade", "Peach tea"]
ALIASES = ["tea", "juice", "fresh-brewed coffee", "ICED TEA WITH LEMON WEDGES"]
PACKAGE = "Coffee, decaf, tea, iced water & juice"

def drink_sets():
    yield []
    for d in SINGLE + ALIASES:
        for a in AMOUNTS:
            yield [(d, a, None)]
    for a in [None, 3, 10]:
        yield [("Oatmilk", a, None)]
    yield [("Oatmilk", 3, "each")]
    yield [("Coffee", 3, "gal")]
    yield [("Coffee", 3, "each")]          # wrong unit
    yield [("Oatmilk", 2, "gallons")]      # wrong unit
    yield [(PACKAGE, None, None)]
    yield [(PACKAGE, 3, None)]             # package with amount -> invalid
    yield [("mocha", None, None)]
    combos = [["Coffee", "Decaf"], ["Coffee", "Lemonade"], ["Iced tea", "Orange juice", "Peach tea"],
              ["Hot water", "Iced tea"], ["Coffee", "mocha"], ["Coffee", "Coffee"]]
    for names in combos:
        for a in [None, 3]:
            yield [(n, a, None) for n in names]
    yield [("Coffee", 6, None), ("Decaf", 2, None)]
    yield [("Coffee", 2, None), ("Coffee", 6, None)]
    yield [(PACKAGE, None, None), ("Coffee", 6, None)]
    yield [(PACKAGE, None, None), ("Orange juice", None, None)]
    yield [(PACKAGE, None, None), ("Lemonade", 4, None)]
    yield [("Oatmilk", 3, None), ("Coffee", 4, None)]

def bev_cases():
    for item, drinks, guests in product(BEV_ITEMS, list(drink_sets()), GUESTS):
        reqs = [DrinkRequest(m, q, u) for m, q, u in drinks]
        r = calculate_bev_item(item, reqs, guests)
        yield {
            "input": {"item": item, "drinks": [{"menu": m, "quantity": q, "unit": u} for m, q, u in drinks], "guests": guests},
            "output": {
                "status": r.status, "text": r.text,
                "drinks": [[d.drink, frac(d.amount), d.unit, d.from_guests] for d in r.drinks],
                "lines": [[l.supply, l.quantity, list(l.reasons)] for l in r.lines],
                "not_on_menu": list(r.not_on_menu), "gallons_each": r.gallons_each, "cups_each": r.cups_each,
            },
        }

def recipe_cases():
    names = list(load_recipe_book().names()) + ["lemonade", "mocha", ""]
    sizes = [{}, {"gallons": 1}, {"gallons": 2.5}, {"gallons": 8}, {"guests": 40}, {"guests": 1},
             {"gallons": 2, "guests": 40}, {"gallons": 0}, {"guests": -3}]
    for name, extra in product(names, sizes):
        args = {"recipe": name, **extra}
        r = run_recipe_tool(args)
        yield {
            "input": args,
            "output": {
                "status": r.status, "text": r.text, "recipe": r.recipe, "gallons": frac(r.gallons),
                "from_guests": r.from_guests,
                "ingredients": [[i.name, frac(i.amount), i.unit, i.fill] for i in r.ingredients],
                "steps": list(r.steps),
            },
        }

for path, cases in [(sys.argv[1], bev_cases()), (sys.argv[2], recipe_cases())]:
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, sort_keys=True) + "\n")
