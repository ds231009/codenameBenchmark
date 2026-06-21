"""Typed exceptions for clue/guess validation failures.

Previously every validation failure in Game was a plain ValueError, so
the only way to know *what kind* of mistake an LLM made was to parse
its error message string -- brittle, and not something you want to
build stage-2 analysis on top of. These subclasses let Game branch on
`isinstance(e, ...)` to classify errors into stats buckets instead.

The format/rule split matters for analysis: a "format" error means the
model didn't follow the output template at all (e.g. no brackets); a
"rule" error means it followed the format but broke a game rule (e.g.
guessed a word not on the board, or gave a clue that's already on the
board). Those are pretty different failure modes worth counting
separately.
"""


class ClueFormatError(ValueError):
    """The codemaster's raw response couldn't be parsed into (word, count)."""


class ClueRuleError(ValueError):
    """The clue was parseable but breaks a rule (count <= 0, word is on the board)."""


class GuessFormatError(ValueError):
    """The guesser's raw response couldn't be parsed into [word]."""


class GuessRuleError(ValueError):
    """The guess was parseable but isn't a valid, unrevealed word on the board."""
