"""The prompt that asks the judge model for a verdict."""

from __future__ import annotations

JUDGE_INSTRUCTIONS = """\
You grade an ANSWER to a QUESTION against a REFERENCE.

The REFERENCE has a "Required:" part (what a correct answer must say). It may \
have a "May also:" part (extra things that are fine to mention) and a "Must \
not:" part (things a correct answer must not recommend, give or state as its \
answer).

Rules:
- PASS only if the answer states everything in "Required:" and its own \
recommendation or answer does nothing listed in "Must not:".
- Same meaning in different words is the same: "gal", "gallon" and \
"5-gallon" are equal; "a", "one" and "1" are equal.
- Grade what the answer recommends or gives as its answer. Explanations, \
reasons and working are extra: they pass if correct and if they do not change \
the recommendation.
- Mentioning another option only to explain or rule it out passes.
- Offering a "Must not:" item as an acceptable alternative fails.
- Correct extra details (another item, an alias, a condition) pass, as long \
as the recommendation for the question asked still meets "Required:".
- A wrong number, a wrong count or a missing "Required:" fact fails.
- Hedging between values fails.
- Saying "I don't know" and then giving what "Must not:" forbids fails.

Examples (reference "Required: 50 cold cups. Must not: give any other number \
of cups."):
- "50 cold cups, not 30, because you add 20 extras" -> PASS
- "50 cold cups, though 30 would also be fine" -> FAIL
Example (reference "Required: lemons."):
- "lemons, plus lemon tongs if hot water is ordered" -> PASS
Example (reference "Required: peach tea."):
- "peach tea (a cold drink, served in cold cups)" -> PASS

Reply with the single word PASS or FAIL first, then a short reason.
"""

JUDGE_TEMPLATE = """\
{instructions}
QUESTION:
{question}

REFERENCE:
{reference}

ANSWER:
{answer}
"""


def build_prompt(question: str, reference: str, answer: str) -> str:
    return JUDGE_TEMPLATE.format(
        instructions=JUDGE_INSTRUCTIONS,
        question=question.strip(),
        reference=reference.strip(),
        answer=answer.strip(),
    )
