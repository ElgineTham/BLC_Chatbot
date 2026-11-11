# Spec 002: Beverage pull sheet from a BEO

- **Status:** approved (revision 1)
- **Date:** 2026-11-10

## 1. Goal
Before an event, employees fill out a pull sheet: the supplies needed for the items on the event's BEO (Banquet Event Order). This spec covers only the **Beverages** section. From one BEO's guest count and beverage lines, the engine works out how many gallons of each drink are ordered (including drinks bundled in package lines), which cambros to bring, any add-on items (e.g. oatmilk), and the beverage supplies (cups, sugar, stir sticks, tea packets…) from JSON menu and rules files that staff maintain. It is deterministic, with no LLM: the same BEO and files always give the same pull sheet, and every line can be traced back to the entries that produced it. One pull sheet is made per BEO (per page set), not per event.

## 2. Out of scope
- The Food, Serving utensils, Always bring and Optional sections.
- Food items, box meals (including bottled water in box meals) and any non-beverage line. A BEO line not on the beverage menu is listed under "check by hand" (§4.5).
- Reading the Special Instructions box (e.g. "Leave iced water", notes asking for oatmilk). Only Menu Selections lines are used.
- Reading BEO photos or PDFs. The BEO is given as a small markdown file (§4.4) or as Python objects.
- Combining several BEOs of one event (e.g. "BEO Series 1 of 2") into one pull sheet.
- Fuzzy or LLM matching of names. Names match exactly after normalization (§4.2).
- Showing reasons in the CLI output (they exist in the API only).
- Writing the real `data/pull_sheet/` files (the user does this), and any change to `ingest.py` or `chat.py`.

## 3. Interface contract

```python
# scripts/pull_sheet.py
from fractions import Fraction

ROOT: Path                          # project root (parent of scripts/)
DEFAULT_RULES_DIR: Path             # ROOT / "data" / "pull_sheet"
MENU_FILE = "menu/beverages.json"   # relative to the rules dir
RULES_FILE = "rules/beverages.json"  # relative to the rules dir
GALLON = "gallon"
EACH = "each"
GUESTS_PER_GALLON = 25
PER_VALUES: tuple[str, ...] = ("event", "guest", "guest+extra", "item", "unit")
TICK = "✓"                          # shown for "bring it, no count" supplies
NOT_ON_MENU = "not on beverage menu"
UNKNOWN_UNIT = "unknown unit"


class RuleFileError(ValueError):
    """The beverage menu or rules file is missing or invalid.
    Attributes: path: Path (the offending file); line: int | None (1-based line
    of a JSON syntax error; None for all other problems).
    str(err) contains the file name, the line number when set, and otherwise the
    location of the offending entry inside the file, written with double quotes
    around object keys and [n] for array positions (e.g. `supplies[3].per`,
    `items["Coffee"].unit`, `packages["Coffee, decaf, tea, iced water & juice"].includes[1]`)."""


class BeoError(ValueError):
    """The BEO text is invalid.
    Attribute: line: int | None (1-based line number, None when not tied to a line)."""


class Catalog:
    """Opaque: the validated menu and rules. Fields are NOT part of the contract;
    build it only with load_catalog()."""


def load_catalog(base_dir: Path = DEFAULT_RULES_DIR) -> Catalog:
    """Read and validate base_dir/MENU_FILE and base_dir/RULES_FILE.
    Raises RuleFileError on any problem listed in §4.3."""


@dataclass(frozen=True)
class BeoLine:
    name: str          # Description as written on the BEO (stripped, non-empty)
    qty: Fraction      # > 0
    unit: str          # Delivery UOM as written (stripped); "" when blank


@dataclass(frozen=True)
class Beo:
    guests: int                    # the BEO's Guest Count, >= 1
    lines: tuple[BeoLine, ...]     # Menu Selections lines with Qty > 0, in BEO order; may be empty


def parse_beo(text: str) -> Beo:
    """Parse the BEO markdown format of §4.4. Raises BeoError on any problem listed there."""


@dataclass(frozen=True)
class PullLine:
    supply: str                # display name (§4.5)
    quantity: int | None       # >= 1, or None for a tick (shown as TICK)
    reasons: tuple[str, ...]   # see §4.5


@dataclass(frozen=True)
class Skipped:
    line: BeoLine
    problem: str               # NOT_ON_MENU or UNKNOWN_UNIT


@dataclass(frozen=True)
class PullSheet:
    guests: int
    lines: tuple[PullLine, ...]     # Beverages section: cambros, then add-ons, then supplies (§4.5); may be ()
    skipped: tuple[Skipped, ...]    # BEO lines not used, in BEO order


def build_pull_sheet(catalog: Catalog, beo: Beo) -> PullSheet:
    """Pure function; does not mutate its inputs. Never raises for a Beo whose
    fields satisfy the constraints above."""


def format_pull_sheet(sheet: PullSheet) -> str:
    """Plain-text rendering, exact format in §4.6."""


def main(argv: list[str] | None = None) -> int:
    """CLI, see below. argv excludes the program name; None means sys.argv[1:]."""
```

CLI:
- `poetry run python scripts/pull_sheet.py BEO_FILE [--rules DIR]`; `DIR` defaults to `DEFAULT_RULES_DIR`.
- On success: prints `format_pull_sheet(...)` to stdout and returns 0, even when lines were skipped.
- On `RuleFileError`, `BeoError` or an unreadable `BEO_FILE`: prints one line starting with `error: ` to stderr, nothing to stdout, and returns 1.
- Wrong arguments: argparse's usual behaviour (exit code 2).

Files read (UTF-8): `DIR/menu/beverages.json`, `DIR/rules/beverages.json`, `BEO_FILE`. Nothing is written. Any other files under `DIR` are ignored.

## 4. Inputs and outputs

### 4.1 Markdown tables (BEO file only)
- A table row is a line whose first non-whitespace character is `|` (the leading `|` is required). Cells are the text between `|` separators, stripped. A trailing `|` is optional, so to leave the last cell empty write it explicitly: `| Oatmilk | 1 | |`.
- Consecutive table rows form one table. Its first row is the header. Its second row must be a separator row: every cell is non-empty and consists only of `-`, `:` and spaces.
- Header names match case-insensitively after stripping. The header must be exactly the column set of §4.4; columns may appear in any order. Every row must have the same number of cells as the header.
- All non-table lines (headings, notes, blank lines) are ignored.

### 4.2 Normalization and numbers
- **Names** (item names, `also_written_as` entries, package lines, BEO descriptions, supplies): `casefold`, then collapse whitespace runs to one space and strip. Two names are the same if their normalized forms are equal. Punctuation is kept, so `Fresh-brewed coffee` ≠ `Fresh brewed coffee`.
- Names may contain commas and other punctuation; the JSON files store lists as arrays.
- **BEO units:** normalized like names. `""` is blank. A unit `u` means gallons if `u` is `gallon` or `gallons`, and means each if `u` is `each`. Anything else is unknown.
- **Tags** are written in capitals: each must match `[A-Z0-9-]+` exactly (no case folding), e.g. `HOT`, `COFFEE`, `HOT-WATER`. Tags are compared exactly, so a lowercase tag is an error, never a different tag.
- **Numbers:** in the JSON files, `qty`, `gallons`, `guests_up_to` and `extra` are JSON numbers (booleans are not numbers), converted exactly, never through float: `0.1` means exactly 1/10. In the BEO, `Qty` is a decimal (`2`, `1.5`, `.5`) or a fraction `a/b`, parsed exactly into `Fraction`.
- **Rounding guests to gallons:** `gallons = max(1, round_half_up(guests / 25))`, i.e. below .5 rounds down and .5 or more rounds up, and the result is at least 1. Examples: 70 → 3, 60 → 2, 63 → 3 (2.52), 62 → 2 (2.48), 25 → 1, 10 → 1.

### 4.3 Menu and rules files

**`menu/beverages.json`** is one JSON object (UTF-8) with these keys:

```json
{
  "items": {
    "Coffee": {
      "unit": "gallon",
      "also_written_as": ["Fresh-brewed coffee"],
      "tags": ["HOT", "COFFEE"]
    },
    "Orange juice": {"unit": "gallon", "also_written_as": [], "tags": ["COLD", "JUICE"]},
    "Oatmilk": {"unit": "each", "also_written_as": [], "tags": []}
  },
  "packages": {
    "Coffee, decaf, tea, iced water & juice": {
      "includes": ["Coffee", "Decaf", "Hot water", "Iced water"],
      "placeholders": {"JUICE": "Orange juice"}
    }
  }
}
```

| Key | Type | Meaning |
|---|---|---|
| `items` | object, required, at least one entry | Key: the item's display name (non-empty after strip). Value: an item object |
| item `unit` | string, required: `gallon` or `each` (case-insensitive) | `gallon`: a drink served from cambros. `each`: an add-on counted in pieces, no cambro (e.g. Oatmilk) |
| item `also_written_as` | array of non-empty strings, required (may be empty) | Exact BEO descriptions for this item, e.g. `Fresh-brewed coffee` |
| item `tags` | array of tags, required (may be empty) | Categories rules can target, e.g. `HOT`, `COFFEE` |
| `packages` | object, optional (missing = none) | Key: a package line, i.e. a BEO description that bundles several drinks. Value: a package object |
| package `includes` | array of item names, required (may be empty) | `gallon` items the line always stands for |
| package `placeholders` | object, optional (missing = none) | Key: a tag. Value: the default item name. A **placeholder** stands for "whichever item with that tag the BEO means" (§4.5 step 2) |

A package must include at least one item or placeholder. Unknown keys anywhere in the menu are an error, so typos like `"also_writen_as"` are caught.

**`rules/beverages.json`** is one JSON object (UTF-8) with these keys:

```json
{
  "cambros": [
    {"supply": "5 gal cambro", "gallons": 5},
    {"supply": "2 gal cambro", "gallons": 2},
    {"supply": "1 gal cambro", "gallons": 1}
  ],
  "supplies": [
    {"supply": "hot-cups", "qty": 1, "per": "guest+extra", "when_tagged": "HOT"},
    {"supply": "Cocktail napkins", "tick": true},
    {"supply": "Creamer", "tick": true, "when_tagged": "COFFEE"},
    {"supply": "Sugar", "qty": 1, "per": "event", "when_tagged": "COFFEE"}
  ],
  "extras": [
    {"guests_up_to": 20, "extra": 10},
    {"guests_up_to": 50, "extra": 20},
    {"guests_up_to": 100, "extra": 50},
    {"guests_up_to": null, "extra": 100}
  ]
}
```

| Key | Type | Meaning |
|---|---|---|
| `cambros` | array, required, at least one entry | Cambro sizes you own |
| cambro `supply` | non-empty string, required | Display name, e.g. `5 gal cambro` |
| cambro `gallons` | number > 0, required | Capacity in gallons |
| `supplies` | array, optional (missing = none) | Supply rules, in the order lines appear on the pull sheet |
| supply `supply` | non-empty string, required | What to bring |
| supply `qty` | number > 0 | Amount per `per`. Required unless `tick` is true; not allowed with a tick |
| supply `per` | one of `PER_VALUES` (case-insensitive) | What `qty` is multiplied by (§4.5). Required with `qty`; not allowed with a tick |
| supply `tick` | `true` | "Bring it, no count"; shown as `✓`. Optional; when present it must be `true` |
| supply `when_tagged` | tag string or `null`; optional | Which ordered items the rule applies to; missing or `null` = any ordered item |
| `extras` | array, optional | Tiers for `guest+extra` rules |
| extra `guests_up_to` | positive integer, or `null` for "any larger event", required | Upper bound of the tier (inclusive) |
| extra `extra` | integer ≥ 0, required | Amount added by `guest+extra` rules for that tier |

The example tiers mean: up to 20 guests +10, 21–50 +20, 51–100 +50, more than 100 +100. Unknown keys anywhere in the rules file are an error.

**`load_catalog` raises `RuleFileError`** (with `path`; `line` only for JSON syntax errors) when:
1. Either file is missing.
2. A file is not valid JSON (`line` is the JSON error's line).
3. A file does not match its layout above: wrong top-level type, missing required key, unknown key, wrong value type, empty name, empty string in a list, or a number out of its range.
4. A supplies entry has both `tick` and `qty`/`per`, has neither, has `qty` without `per` or `per` without `qty`, or has `tick` other than `true`.
5. A tag (menu `tags`, placeholder key or `when_tagged`) does not match `[A-Z0-9-]+` (e.g. `hot` or `Hot` instead of `HOT`).
6. A menu `unit` is not `gallon` or `each` (case-insensitive).
7. Two names clash (normalized): any item name, `also_written_as` entry or package line equals another one, within or across items and packages.
8. A package's `includes` or placeholder default names something that isn't an item name or names an `each` item; an item appears twice in one package (directly or as a placeholder default); a package includes nothing; or a placeholder's default item does not have the placeholder's tag.
9. Two cambros have the same capacity.
10. A `per` is not in `PER_VALUES`.
11. `when_tagged` names a tag that no item has.
12. The same supply (normalized) is a tick in one entry and numeric in another.
13. A supply name (normalized) equals a cambro name or an `each` item name, or two cambro names are equal.
14. Two `extras` entries have the same `guests_up_to`, or there is not exactly one entry with `guests_up_to` `null`.
15. A supplies entry uses `guest+extra` and `extras` is missing or empty.

### 4.4 BEO text (`parse_beo`)
```markdown
Guest Count: 70

| Description | Qty | Delivery UOM |
|---|---|---|
| ~Beverages~ | 0 | |
| Coffee, decaf, tea, iced water & juice | 70 | |
| Orange juice | 70 | |
| Fresh-brewed coffee | 2 | Gallon |
| Oatmilk | 1 | Each |
```
- Exactly one line matching `Guest Count: <int>` (case-insensitive; whitespace allowed before, after and around `:`), integer ≥ 1.
- Zero or one table with columns `Description | Qty | Delivery UOM` (§4.1). Extra columns are not allowed. Zero tables means no lines.
- `Qty` is a number ≥ 0. Rows with `Qty` 0 (section headers like `~Beverages~`, spacer rows) are dropped and do not appear in `Beo.lines`.
- Rows with `Qty` > 0 need a non-empty `Description`; `Delivery UOM` may be blank.
- All other lines are ignored.
- `BeoError` for: missing, duplicate or invalid `Guest Count` line; bad table or a second table; invalid or negative `Qty`; empty `Description` with `Qty` > 0.
- `BeoError.line` is set for every error tied to a line: the invalid `Guest Count` line, the **second** `Guest Count` line, the first row of a second table, a bad header or separator row, and the offending data row. It is `None` only when something is missing (no `Guest Count` line).

### 4.5 How the beverage list is computed (`build_pull_sheet`)
1. **Match** each BEO line by normalized description:
   - **Package line** (matches a key of `packages`):
     - blank unit → `qty` is a guest count → each included item gets `max(1, round_half_up(qty / 25))` gallons;
     - gallons unit → each included item gets `qty` gallons;
     - any other unit → `Skipped(line, UNKNOWN_UNIT)`.
   - **Item** (matches an item name or other name):
     - `gallon` item: blank unit → guest count, converted as above; gallons unit → `qty` gallons; otherwise `UNKNOWN_UNIT`.
     - `each` item: each unit → `qty` pieces; otherwise `UNKNOWN_UNIT`.
   - **No match** → `Skipped(line, NOT_ON_MENU)`.
   - Skipped lines take no further part.
2. **Ordered amount per item:**
   - **Placeholders first.** A package placeholder `<tag>: <default item>` (e.g. `"JUICE": "Orange juice"`) stands for "whichever item with that tag the BEO means". If **any** item with that tag has its own matched line on the BEO, the placeholder contributes nothing. Otherwise it contributes the package amount to the default item. Examples with the package at 3 gal:
     - plus Orange juice 3 gal and Pomegranate juice 4 gal → Orange juice 3, Pomegranate juice 4;
     - plus Pomegranate juice 4 gal only → Pomegranate juice 4, no Orange juice;
     - plus Pomegranate juice 1 gal only → Pomegranate juice 1 (the listed amount wins, even if smaller);
     - no juice lines → Orange juice 3.
   - `own` is the sum over the item's own lines.
   - `pkg` is the sum over all package lines that include it directly or through a placeholder that was not dropped.
   - The ordered amount is **the larger of `own` and `pkg`** (count once, don't add). For example, the package "…& juice" for 70 guests (3 gal of Orange juice) plus a separate "Orange juice" line for 70 guests (3 gal) → 3 gal, not 6.
   - The **ordered items** are those with an ordered amount > 0.
   - **Item order**, used everywhere items are listed (cambro reasons, add-on lines, item names in reasons): by each item's first contributing BEO line; items that first appear on the **same** package line follow that package's `includes` order, then its placeholder defaults in the order written in `placeholders`. Example: package line `Coffee; Decaf; Hot water; Iced water` + `JUICE → Orange juice` → Coffee, Decaf, Hot water, Iced water, Orange juice. The order never depends on anything else.
3. **Cambros.** Each ordered `gallon` item gets its own cambros; different items never share one. Pick cambros **largest first** for its ordered amount: let `L` be the largest capacity. While the remaining gallons are ≥ `L`, take one `L` cambro. Then, if any gallons remain, take one cambro of the **smallest capacity that holds the rest**. With 1, 2 and 5: 7 → 5 + 2; 6 → 5 + 1; 3 → 5; 8 → 5 + 5; 12 → 5 + 5 + 2; 1 → 1.
   - One `PullLine` per capacity used, ordered largest capacity first. `supply` is the cambro name, and `quantity` is the total across items.
   - `reasons`: one per item using it, in **item order** (below). Each starts with `rules/beverages.json cambros[<i>]` (the cambro's 0-based position) and contains the item's display name.
4. **Add-ons.** Each ordered `each` item is one `PullLine`:
   - `supply` is the item's display name and `quantity` is `ceil(ordered amount)`.
   - Lines are in item order.
   - One reason, starting with `menu/beverages.json` and containing the display name.
5. **Supplies.** First the **cup count base** `G`: the largest of the BEO's Guest Count and the `qty` of every matched (not skipped) line read as a guest count (blank unit, step 1). Example: Guest Count 50 with the package line at 70 → `G` = 70. `G` is used wherever this step says `guests`; `PullSheet.guests` and the first output line still show the BEO's Guest Count.

   For each supplies entry, its **matching items** are the ordered items (`gallon` and `each`) that have its `when_tagged` tag, or all ordered items if there is none. An entry with no matching items contributes nothing. Otherwise it contributes once (a tag decides **whether** an entry applies, not how many times):

   | Per | Contribution |
   |---|---|
   | `event` | `qty` (once, however many items match) |
   | `guest` | `qty × guests` (once, however many items match) |
   | `guest+extra` | `qty × guests + extra` (once, however many items match), with `extra` from the `extras` entry with the smallest `guests_up_to` ≥ `guests`, else the `null` entry (the tier is chosen by `G` too) |
   | `item` | `qty × number of matching items` |
   | `unit` | `Σ over matching items of qty × ceil(ordered amount)` |

   A tick entry contributes a tick. Example: hot-cups `guest+extra` tagged `HOT`, `G` = 70, with Coffee and Decaf both ordered → 70 + 50 = 120, not 240. With Guest Count 50 and the package line at 70 → also 120 (base 70, tier ≤100 → +50).
6. **Pull once, don't add up.** When several entries contribute to the same supply (normalized name), the line uses the **largest** contribution, then rounds it **up** to an integer. If the supply's entries are ticks, the line is a tick (`quantity` `None`). The display name and the line's position come from the **first entry in `supplies` that names the supply, whether or not that entry applies**. Example: `supplies[0]` Cups tagged `COLD` (no cold drink ordered), `supplies[1]` Sugar, `supplies[2]` cups tagged `HOT` (applies) → the sheet lists `Cups` (named as in `supplies[0]`) before Sugar.
   - Reasons: one per contributing entry, in array order. Each starts with `rules/beverages.json supplies[<i>]` (0-based position) and, for `item` and `unit` entries, contains the display name of every matching item, in item order.
7. **Order of `lines`:** cambros (step 3), then add-ons (step 4), then supplies (step 6).

### 4.6 Text output (`format_pull_sheet`)
Example for the §4.4 BEO plus a `Cascade Breakfast | 70 | Packages` line, with a shortened supplies table:
```
Pull sheet for 70 guests

Beverages
- 5 gal cambro: 5
- Oatmilk: 1
- hot-cups: 120
- cold-cups: 120
- Cocktail napkins: ✓
- Creamer: ✓
- Stir sticks: 1
- Sugar: 1

Not used (check by hand):
- Cascade Breakfast, 70 Packages: not on beverage menu
```
- First line `Pull sheet for <guests> guests`, then a blank line.
- `Beverages`, then one `- <supply>: <quantity>` line per `PullLine` (`<quantity>` is `✓` for a tick), or `- (none)` if there are none.
- Only when `skipped` is not empty: a blank line, `Not used (check by hand):`, then one line per skipped line in order: `- <name>, <qty> <unit>: <problem>` (when the unit is blank: `- <name>, <qty>: <problem>`). `<name>` and `<unit>` are as written on the BEO; `<qty>` is the integer if whole, else the shortest exact decimal if one exists, else `a/b`.
- The text ends with exactly one `\n`.

## 5. Edge cases
Shorthand: a supplies entry is written `Supply | qty | per | tag` (or `Supply | ✓ | tag` for a tick); a cambro as its capacity.

- EC-1: Package `Coffee, decaf, tea, iced water & juice`, qty 70, blank unit → Coffee, Decaf, Hot water, Iced water and Orange juice each get 3 gal (70 / 25 = 2.8 → 3) → each gets one 5 gal cambro (largest first).
- EC-2: Same package with `1 Gallon` → 1 gal of each of the five.
- EC-3: Guests-to-gallons rounding: 60 → 2, 62 → 2, 63 → 3, 75 → 3, 87 → 3 (3.48), 88 → 4 (3.52), 25 → 1, 10 → 1, 1 → 1.
- EC-4: Package for 70 guests plus a separate `Orange juice` line for 70 guests → Orange juice 3 gal, not 6 (the juice placeholder is dropped because a juice is listed).
- EC-5: Package for 1 gal plus a separate `Fresh-brewed coffee` line of 3 gal → Coffee 3 gal (larger), not 4; package for 3 gal plus Coffee 1 gal → Coffee 3 gal.
- EC-5a: Juice placeholder (`juice -> Orange juice`, package 3 gal): with Orange juice 3 and Pomegranate juice 4 → OJ 3, Pomegranate 4; with only Pomegranate juice 4 → Pomegranate 4 and no OJ; with only Pomegranate juice 1 → Pomegranate 1; with no juice lines → OJ 3.
- EC-5b: A juice line that is skipped (e.g. `Mango juice` not on the menu, or `Orange juice` with unit `Each`) does not drop the placeholder; the package still gives Orange juice.
- EC-5c: The package's `tea` is always Hot water: package plus `Iced tea with lemon wedges` 5 gal → Hot water from the package and Iced tea 5 gal, both kept.
- EC-6: Two own lines for the same item (`Fresh-brewed coffee` 2 gal and 3 gal) → 5 gal (own lines add up) → one 5 gal cambro.
- EC-7: `Hot water with an assortment of black, green, and herbal tea bags` (commas in the name) matches its other name exactly.
- EC-8: Description `  FRESH-BREWED   coffee ` matches `Fresh-brewed coffee`; `Fresh brewed coffee` (no hyphen) → `NOT_ON_MENU`.
- EC-9: `Oatmilk`, 1, `Each` → add-on line `Oatmilk: 1`, no cambro.
- EC-10: `Oatmilk`, 1, `Gallon` → `UNKNOWN_UNIT`; `Fresh-brewed coffee`, 2, `Each` → `UNKNOWN_UNIT`; package with unit `Packages` → `UNKNOWN_UNIT`.
- EC-11: `Fresh-brewed coffee`, 70, blank unit → treated as 70 guests → 3 gal.
- EC-12: `Cascade Breakfast`, 70, `Packages` and food lines → `NOT_ON_MENU`; they trigger no rules.
- EC-13: Rows with `Qty` 0 (e.g. `~Beverages~`, `~Additional Items~`) → dropped by `parse_beo`; they appear neither in `lines` nor in `skipped`.
- EC-14: Cambros with 1, 2, 5: coffee 7 gal and hot water 2 gal → `5 gal cambro: 1`, `2 gal cambro: 2`, listed 5 then 2; the 2 gal line has two reasons, coffee first.
- EC-15: Coffee 1 gal and decaf 1 gal → two 1 gal cambros, never one 2 gal shared.
- EC-16: `cambros` with only a 3 gal size, 7 gal ordered → 3 + 3 + 3.
- EC-17: Extras `20|10, 50|20, 100|50, (empty)|100` with `hot-cups | 1 | guest+extra | hot`: 20 → 30, 21 → 41, 50 → 70, 51 → 101, 100 → 150, 101 → 201, 120 → 220.
- EC-18: hot-cups when tagged `HOT` and cold-cups when tagged `COLD`: only hot drinks ordered → hot-cups only; both ordered → both lines, each `guests + extra`. Coffee, Decaf and Hot water (all `HOT`) at 70 guests → hot-cups 120, not 360.
- EC-19: Sugar `1` per `event` tagged `COFFEE` and Sugar `1` per `event` tagged `HOT-WATER`, both ordered → Sugar 1 with two reasons.
- EC-20: Cups `1` per `guest` for `COFFEE` and `1.5` per `guest` for `HOT-WATER`, both ordered, 100 guests → 150 (largest), not 250.
- EC-21: Creamer `✓` tagged `COFFEE` → `Creamer: ✓` when coffee or decaf (tagged `COFFEE`) is ordered, otherwise no line.
- EC-22: Cocktail napkins `✓` with no `when_tagged` (missing or `null`) → appears whenever at least one item is ordered; absent when every line is skipped.
- EC-23: `0.1` per `guest` × 30 guests → exactly 3, not 4 (exact arithmetic); 1.5 per guest × 33 → 49.5 → 50.
- EC-24: A tagged rule matching an `each` item: `Stir sticks | 1 | item | coffee` with Oatmilk tagged `COFFEE` → counts Oatmilk as a matching item.
- EC-25: Menu errors (`RuleFileError` on `menu/beverages.json`): package includes `Cofee` (no such item); package includes an `each` item; package line equal to an item's `also_written_as` entry; placeholder `"JUICE": "Coffee"` where Coffee lacks the `JUICE` tag; placeholder default not an item; unit `quart`; misspelled key `also_writen_as`; `tags` given as a string instead of an array.
- EC-25a: Rules errors (`RuleFileError` on `rules/beverages.json`, message naming the entry, e.g. `supplies[3]`): `when_tagged` `HOT-DRNK`; an entry with both `tick` and `qty`; an entry with `qty` but no `per`; `tick: false`; `qty` `0`, `-1` or `"1"` (a string); `qty` `true`; Sugar a tick in one entry and numeric in another; supply named `Oatmilk` when Oatmilk is an `each` item; `extras` with two `null` bounds or none; `guest+extra` with no `extras`; duplicate cambro capacity; missing or empty `cambros`; misspelled key `when_taged`.
- EC-25b: A trailing comma or missing quote in either JSON file → `RuleFileError` with `line` set to the JSON error's line.
- EC-26: In the menu, `packages` and `placeholders` may be missing; in the rules, `supplies` and `extras` may be missing (if no entry uses `guest+extra`). Key order inside objects does not matter.
- EC-27: BEO errors: no `Guest Count` line, two of them, `Guest Count: 0` or `2.5`; `Qty` `-1` or `abc`; empty Description with Qty 2; a second table → `BeoError`.
- EC-28: A BEO whose lines are all skipped, or with no table → `Beverages` shows `- (none)`.
- EC-29: Other files in the rules dir (e.g. a malformed `rules/food.json`) → ignored.
- EC-30: Cup count base `G` (§4.5 step 5): Guest Count 50 + package line 70 (blank unit) → hot-cups and cold-cups each 70 + 50 = 120; Guest Count 70 + package line 50 → `G` 70 → 120; Guest Count 15 + package line 30 → `G` 30 → 30 + 20 = 50 (tier chosen by `G`, not by 15); a skipped blank-unit line (e.g. `Mango juice | 200 |` not on the menu) does not raise `G`; gallon lines (`Fresh-brewed coffee | 90 | Gallon`) do not count toward `G`; the first output line still says `Pull sheet for 50 guests`.
- EC-31: Item order: the package line `Coffee, decaf, tea, iced water & juice` at 70 → the `5 gal cambro` reasons name Coffee, Decaf, Hot water, Iced water, Orange juice in that order, identically across separate Python processes (different `PYTHONHASHSEED`).
- EC-32: Supply position and name from the first naming entry: `supplies[0]` `Cups | 1 | guest | COLD` (no cold drink), `supplies[1]` `Sugar | 1 | event | COFFEE`, `supplies[2]` `cups | 1 | guest | HOT`, only Coffee ordered → lines `Cups: <n>` then `Sugar: 1`; the Cups line has one reason, `supplies[2]`.
- EC-33: Tags must be capitals: menu tag `hot`, placeholder key `juice` or `when_tagged: "Hot"` → `RuleFileError`.
- EC-34: BEO rows: a line without a leading `|` (`Coffee | 3 | Gallon`) is not a table row and is ignored; `| Oatmilk | 1 |` has two cells and gives `BeoError` for the wrong cell count; `   Guest Count: 70   ` is valid; a second `Guest Count` line on line 3 gives `BeoError.line == 3`; a missing `Guest Count` gives `line` `None`.
- EC-35: Error locations use double quotes: an invalid unit for Coffee gives a message containing `items["Coffee"].unit`.

## 6. Acceptance criteria
- **AC-1:** `load_catalog` on a valid directory returns a `Catalog` that `build_pull_sheet` accepts; each condition in §4.3 (1–15) raises `RuleFileError` whose `path` is the offending file; JSON syntax errors set `line`, other problems name the offending entry in the message.
- **AC-2:** `parse_beo` returns the guest count and the `Qty` > 0 lines in order, with exact `Fraction` quantities and `""` for a blank unit; each invalid case in §4.4 raises `BeoError` (EC-13, EC-27).
- **AC-3:** Package lines expand into their included items with the same amount each, from gallons or from guests at 25 per gallon with half-up rounding and a minimum of 1 (EC-1 to EC-3, EC-11).
- **AC-4:** Placeholders are dropped when any item with their tag has its own matched line, else they go to their default item; an item's ordered amount is then the larger of its own lines' sum and its package sum (EC-4 to EC-6, EC-5a to EC-5c).
- **AC-5:** Each ordered `gallon` item gets its own cambros, chosen largest first; cambro lines come first, one per capacity used, largest first, with totals and one reason per item (EC-14 to EC-16).
- **AC-6:** Ordered `each` items appear as add-on lines with their count, after the cambros and before the supplies, and get no cambro (EC-9).
- **AC-7:** `event`, `guest`, `guest+extra`, `item` and `unit` entries compute contributions exactly as in §4.5 step 5, including the extras tiers at their boundaries (EC-17, EC-18, EC-24).
- **AC-8:** Several entries for the same supply give one line with the largest contribution, rounded up; ticks give `quantity` `None` (EC-19 to EC-23).
- **AC-9:** Lines not on the menu and lines with unknown units appear in `skipped` in BEO order with the right problem and affect nothing else (EC-10, EC-12).
- **AC-10:** Every cambro reason starts with `rules/beverages.json cambros[<i>]`, every supply reason with `rules/beverages.json supplies[<i>]`, every add-on reason with `menu/beverages.json`, and reasons name the items as described in §4.5.
- **AC-11:** `format_pull_sheet` produces exactly the format of §4.6, including `✓`, `- (none)`, blank-unit skipped lines and the conditional `Not used (check by hand):` block.
- **AC-12:** `main([beo_path, "--rules", dir])` prints the formatted sheet to stdout and returns 0; with a bad rules dir, a bad BEO or a missing BEO file it prints one `error: ` line to stderr, nothing to stdout, and returns 1.
- **AC-13:** The same catalog and BEO always give an equal `PullSheet` and identical text, also across separate Python processes (EC-31).
- **AC-14:** `guest` and `guest+extra` entries use the cup count base `G` (the larger of the Guest Count and every matched blank-unit line's `qty`), including for choosing the extras tier; the header still shows the Guest Count (EC-30).
- **AC-15:** Items are listed in item order (§4.5 step 2), and each supply line's position and display name come from the first `supplies` entry that names it (EC-31, EC-32).
- **AC-16:** Tags must match `[A-Z0-9-]+`; BEO table rows need a leading `|`; `BeoError.line` and `RuleFileError` locations follow §4.4 and §3 (EC-33 to EC-35).

## 7. Non-functional requirements
| ID | Requirement | How verified |
|---|---|---|
| NFR-1 | Deterministic and offline: no LLM, Ollama, Chroma or network use; importing `pull_sheet` does not import langchain, chromadb or ollama. | unit |
| NFR-2 | Exact arithmetic: no float in any quantity, gallon or rounding calculation (EC-3, EC-23). | unit |
| NFR-3 | No new dependencies (standard library only). | manual (review `pyproject.toml`) |
| NFR-4 | `build_pull_sheet` does not mutate its inputs. | unit |
| NFR-5 | `str(RuleFileError)` contains the file name, and either the line number (JSON syntax errors) or the location of the offending entry, with object keys in double quotes (e.g. `supplies[3].per`, `items["Coffee"].unit`). | unit |
| NFR-6 | With the user's real menu and rules files and the example BEOs in `data/pull_sheet/examples/` typed in as markdown, the Beverages list matches what an experienced employee would pull. | manual |

## Revision history
- **Revision 1 (2026-11-10)**, after the first review round:
  - BEO table rows must start with `|`; the trailing `|` is optional (§4.1).
  - `Guest Count` line may have surrounding whitespace, and `BeoError.line` rules are defined (§4.4).
  - Tags must be written in capitals (§4.2, §4.3 #5).
  - Cup count base `G`: guest-based rules use the larger of the Guest Count and the package or blank-unit line quantities; extras still apply on top (§4.5 step 5).
  - Item order is defined for items from the same package line (§4.5 step 2).
  - Supply position and name come from the first entry naming it, whether or not it applies (§4.5 step 6).
  - Error locations use double quotes around object keys (§3).
  - New EC-30 to EC-35 and AC-14 to AC-16.
  - Code and tests: update the existing `scripts/pull_sheet.py` and `tests/test_pull_sheet.py` in place to match Revision 1. Tests that expected the old behaviour (lowercase tags, rows without a leading `|`, `Hot cups` naming in examples, unspecified item order) must be updated. Each validation test must break exactly one rule: e.g. a wrong-header test must use a separator and data rows with the same number of cells as that header, so only the header rule can fail.
