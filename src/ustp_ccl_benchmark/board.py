"""Board state for a single Codenames game."""

import copy


class Board:
    def __init__(self, initial_words: list[dict]):
        self.words = copy.deepcopy(initial_words)

    def get_formatted(self, structure="detailed", show_only_unrevealed=False, filter_by_group=("blue", "red", "assassin")):
        """Formats the board for the LLM prompts."""
        formatted_board = []
        for word in self.words:
            if show_only_unrevealed and word["revealed"]:
                continue

            if word["group"] in filter_by_group:
                if structure == "detailed":
                    formatted_board.append(word)
                elif structure == "codemaster":
                    formatted_board.append({word["word"].upper(): word["group"].upper()})
                elif structure == "word":
                    formatted_board.append(word["word"])
                else:
                    raise ValueError(f"Not a valid structure: {structure}")
        return formatted_board

    def remaining_words(self, groups=("blue", "red", "assassin")):
        """Convenience wrapper around get_formatted: unrevealed word strings
        for the given group(s). Pass a single group name (e.g. "blue") or
        an iterable of group names; defaults to all three groups."""
        if isinstance(groups, str):
            groups = (groups,)
        return self.get_formatted("word", show_only_unrevealed=True, filter_by_group=groups)

    def is_group_cleared(self, group: str) -> bool:
        """True once every word in `group` has been revealed (e.g. all blue found)."""
        return len(self.remaining_words(group)) == 0

    def reveal_word(self, guessed_word: str):
        """Marks a word as revealed and returns it. Returns False if not found."""
        guessed_word = guessed_word.upper()
        for ref_word in self.words:
            if ref_word["word"].upper() == guessed_word:
                ref_word["revealed"] = True
                return ref_word.copy()
        return False
