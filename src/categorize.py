"""Keyword-based transaction categorization driven by config/categories.yaml."""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "categories.yaml"

UNCATEGORIZED = "Uncategorized"


def load_rules() -> dict[str, list[str]]:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f) or {}
    return {category: [kw.lower() for kw in keywords] for category, keywords in data.items()}


def save_rules(rules: dict[str, list[str]]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(rules, f, sort_keys=False, allow_unicode=True)


def categorize(description: str, rules: dict[str, list[str]] | None = None) -> str:
    if rules is None:
        rules = load_rules()
    desc = description.lower()
    for category, keywords in rules.items():
        for kw in keywords:
            if kw in desc:
                return category
    return UNCATEGORIZED


def categorize_all(descriptions: list[str]) -> list[str]:
    rules = load_rules()
    return [categorize(d, rules) for d in descriptions]
