from typing import TypedDict

class ConfigDict(TypedDict, total=False):
    duration: list[dict[str, int]]
    language_config: list[dict[str, int]]
    group_config: list[dict[str, int]]