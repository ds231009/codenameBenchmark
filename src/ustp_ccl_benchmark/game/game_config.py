from pathlib import Path
import random
import copy


class GameConfig:
    def __init__(self, parent):
        self._parent = parent
        self.groupConfig = None
        self.languageConfig = {}
        self.rounds = 0
        self.roundsUntilRefinement = 5

    def setGroupConfig(self, groupConfig: dict):
        if groupConfig.get("blue", 0) <= 0:
            raise ValueError("Game size must be > 0")
        self.groupConfig = groupConfig
        return self

    def setLanguageConfig(self, config: dict):
        if not isinstance(config, dict):
            raise TypeError("Language config must be a dictionary")
        self.languageConfig = config
        return self

    def setDuration(self, rounds: int):
        self.rounds = rounds
        return self

    def setRefinementStep(self, rounds_until_refinement: int):
        self.roundsUntilRefinement = rounds_until_refinement
        return self

    def generateBoard(self) -> list:
        wordlist_path = Path(__file__).parent / "wordlist.txt"
        with open(wordlist_path, "r", encoding="utf-8") as fh:
            raw_board = [line.strip() for line in fh]

        boards = []
        for _ in range(self.rounds):
            pool = raw_board.copy()
            board = []
            for group, count in self.groupConfig.items():
                for _ in range(int(count)):
                    word = pool.pop(random.randrange(len(pool)))
                    board.append({"word": word.lower(), "group": group, "revealed": False})
            boards.append(board)

        return boards

    def setActiveBoard(self, index: int):
        """Load a specific board from the pre-generated list."""
        self.board = copy.deepcopy(self.boards[index])

    def done(self):
        if self.groupConfig is None:
            raise ValueError("Group config must be defined before calling done().")

        self.boards = self.generateBoard()
        self.setActiveBoard(0)
        self._parent.game_config = self
        return self._parent

    def getBoard(
        self,
        structure: str = "detailed",
        show_only_unrevealed: bool = False,
        filter_by_group: list | None = None,
    ) -> list:
        if filter_by_group is None:
            filter_by_group = ["blue", "red", "assassin"]

        result = []
        for word in self.board:
            if show_only_unrevealed and word["revealed"]:
                continue
            if word["group"] not in filter_by_group:
                continue

            if structure == "detailed":
                result.append(word)
            elif structure == "codemaster":
                result.append({word["word"]: word["group"]})
            elif structure == "word":
                result.append(word["word"])
            else:
                raise ValueError(f"Unknown structure '{structure}'.")

        return result

    def revealedWord(self, word: str):
        for entry in self.board:
            if entry["word"].lower() == word.lower():
                entry["revealed"] = True
                return entry.copy()
        return False

    def summary(self) -> dict:
        return {
            "gameSize":       self.groupConfig,
            "languageConfig": self.languageConfig,
            "board":          self.boards,
        }