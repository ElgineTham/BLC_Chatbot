"""Names, statuses and the result of the serving utensils tool (spec 042 3.1)."""

from __future__ import annotations

from dataclasses import dataclass

SERV_TOOL_NAME = "calculate_serving_utensils"
SERV_UTENSILS: tuple[str, ...] = (
    "small tongs", "large tongs", "salad tongs", "dressing/sauce bowl",
    "ladle/sauce spoon", "serving spoon", "spreader/knives", "mayo/mustard",
    "condiments", "honey bear",
)
SERV_UNITS: tuple[str, ...] = ("each", "dozen", "bags", "packages")
SERV_STATUSES: tuple[str, ...] = ("ok", "need_info", "invalid")


@dataclass(frozen=True)
class ServResult:
    status: str
    text: str
    utensils: dict[str, int] | None
    foods: tuple[str, ...] | None
