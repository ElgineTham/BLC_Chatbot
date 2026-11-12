"""The router's system prompt, reply schema and the messages sent to the model."""

from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from blc.router.items import PULL_SHEET_ITEMS

ROUTER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "route": {"type": "string", "enum": ["TOOL", "DOCS"]},
                    "text": {"type": "string"},
                },
                "required": ["route", "text"],
            },
        }
    },
    "required": ["parts"],
}

ITEM_LIST_PLACEHOLDER = "{ITEM_LIST}"

_PROMPT_TEMPLATE = """You route questions from Bay Laurel Catering staff. Split the question into parts and label every part TOOL or DOCS.

A calculator tool knows the beverage pull sheet. Label a part TOOL only when it asks HOW MUCH or HOW MANY of one of these items to make or bring, or whether to bring it:
{ITEM_LIST}
Menu drinks: Coffee, Decaf, Hot water, Brewed hot cider, Ginger Honeycrisp apple cider, Iced water, Iced tea, Orange juice, Lemonade, Peach tea, Oatmilk, and the package "Coffee, decaf, tea, iced water & juice".

Label everything else DOCS: recipes and how to make a drink, ingredient amounts, where things are kept, what a name or package means, prices, schedules, cleaning, and drinks that are not on the menu.

Check each part in this order:
1. Does it ask for an amount to make or bring, or whether to bring something, for one of the items above? If not, it is DOCS.
2. Is the item word used as the thing to bring, or only as an ingredient, a batch size or a place? Words like gallons, sugar and lemons show up in recipes: "how to make 8 gallons of X" asks for a method, and "how much sugar goes in X" asks for an ingredient amount. Those are DOCS. The amount in a recipe question is the batch size; it does not make the question TOOL.
3. If you are still not sure, choose DOCS.

Rules:
- If the question asks several things, write one part per question, in the order asked.
- If it asks how to make a drink and also asks how much to bring, write a DOCS part for the recipe, then a TOOL part for the amount.
- Copy, do not reword. Write each part with the user's own words, exactly as in the question. Do not paraphrase, shorten or change a word. Cut the question only between separate questions. Keep every number, drink name, package name and phrase such as "pull sheet" exactly as written.
- One part per question, not one per drink. "Coffee and lemonade" stays in one part.
- Rewrite only a follow-up. If the latest message cannot be understood without the chat history (for example it only gives an amount, or says "each" or "the same"), write the complete question using the history, and keep every number and drink from the user's message.
- Do not answer the question.

Reply only with JSON in this shape:
{"parts": [{"route": "TOOL", "text": "..."}, {"route": "DOCS", "text": "..."}]}

Examples:
Question: How do I make 8 gallons of mocha?
{"parts": [{"route": "DOCS", "text": "How do I make 8 gallons of mocha?"}]}

Question: How many cambros do I need for 8 gallons of mocha?
{"parts": [{"route": "TOOL", "text": "How many cambros do I need for 8 gallons of mocha?"}]}

Question: How much sugar goes into a batch of chai?
{"parts": [{"route": "DOCS", "text": "How much sugar goes into a batch of chai?"}]}

Question: Do I bring sugar for the chai station?
{"parts": [{"route": "TOOL", "text": "Do I bring sugar for the chai station?"}]}

Question: Where is the matcha kept, and how many cups for 25 guests?
{"parts": [{"route": "DOCS", "text": "Where is the matcha kept?"}, {"route": "TOOL", "text": "How many cups for 25 guests?"}]}

Question: I need 9 gallons of decaf and hot water, how many containers?
{"parts": [{"route": "TOOL", "text": "I need 9 gallons of decaf and hot water, how many containers?"}]}

Question: The coffee, decaf, tea, iced water & juice package is ordered for 110 guests, how many cups should I bring?
{"parts": [{"route": "TOOL", "text": "The coffee, decaf, tea, iced water & juice package is ordered for 110 guests, how many cups should I bring?"}]}

Question: Peach tea for 80 people, what should I pack?
{"parts": [{"route": "TOOL", "text": "Peach tea for 80 people, what should I pack?"}]}

Question: How do I make cold brew, and how many gallons for 60 guests?
{"parts": [{"route": "DOCS", "text": "How do I make cold brew,"}, {"route": "TOOL", "text": "and how many gallons for 60 guests?"}]}

History: the assistant asked "How many gallons of each?" about orange juice and iced tea. Question: 6 each.
{"parts": [{"route": "TOOL", "text": "How many cambros for 6 gallons of orange juice and 6 gallons of iced tea?"}]}

History: the assistant asked "How many gallons of each?" about mocha and chai. Question: 3 each.
{"parts": [{"route": "TOOL", "text": "How many cambros for 3 gallons of mocha and 3 gallons of chai?"}]}"""


def build_item_list() -> str:
    return "\n".join(
        f"- {item} [{', '.join(words)}]" for item, words in PULL_SHEET_ITEMS.items()
    )


# replace() rather than format(): the JSON braces in the template must stay as they are.
ROUTER_PROMPT = _PROMPT_TEMPLATE.replace(ITEM_LIST_PLACEHOLDER, build_item_list())

HISTORY_LABEL = "Chat history:"
QUESTION_LABEL = "Question:"


def format_router_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(empty)"
    return "\n".join(f"{item['role']}: {item['content']}" for item in history)


def build_router_messages(
    history: list[dict[str, str]], question: str
) -> list[BaseMessage]:
    body = (
        f"{HISTORY_LABEL}\n{format_router_history(history)}\n\n"
        f"{QUESTION_LABEL}\n{question}"
    )
    return [SystemMessage(content=ROUTER_PROMPT), HumanMessage(content=body)]
