"""Centralized console logging for the Codenames benchmark.

Replaces the three copy-pasted `log()` functions that used to live in
board.py, game.py and game_set.py separately (and a near-duplicate in
llm.py). Two things changed on top of just de-duplicating:

1. Unknown channel names no longer crash. The old version did
   `colorMap[function]`, a plain dict lookup -- any function name not in
   the map raised a KeyError. This uses `.get()` with a fallback color.
2. There's now a `level` (info/warning/error). It's purely cosmetic
   (color + a "[WARN]"/"[ERROR]" prefix) but it makes retries and real
   failures visually distinct in the console, instead of every line
   being the same color regardless of what happened.
"""

from colorama import Fore, Style, init
from tqdm import tqdm

init(autoreset=True)

# Color per "channel" -- roughly, which part of the pipeline is talking.
_COLOR_MAP = {
    "runGame":     Fore.CYAN,
    "getClue":     Fore.BLUE,
    "getGuesses":  Fore.RED,
    "getGuess":    Fore.YELLOW,
    "handleGuess": Fore.GREEN,
    "saveStats":   Fore.LIGHTCYAN_EX,
    "Guesser":     Fore.GREEN,
    "Codemaster":  Fore.LIGHTCYAN_EX,
}

_LEVEL_PREFIX = {
    "debug": "[DEBUG] ",
    "info": "",
    "warning": "[WARN] ",
    "error": "[ERROR] ",
}


def log(channel: str, *args, level: str = "info", **kwargs):
    """Print a single colored, leveled log line.

    channel: free-form label for where the log came from (e.g.
             "getClue", "Guesser"). Unknown channels just get a neutral
             color instead of raising.
    level:   "debug" | "info" | "warning" | "error". Cosmetic only -- everything
             still prints, nothing is filtered out.
    """
    # 1. Filter out chatty per-turn logs
    if level == "debug":
        return

    if level == "error":
        color = Fore.RED + Style.BRIGHT
    elif level == "warning":
        color = Fore.YELLOW
    else:
        color = _COLOR_MAP.get(channel, Fore.WHITE)

    prefix = _LEVEL_PREFIX.get(level, "")
    message = ", ".join(map(str, (*args, *kwargs.values())))
    formatted_msg = f"{color}[{channel}] {prefix}{message}{Style.RESET_ALL}"
    
    # 2. Route prints through tqdm so the progress bar remains intact at the bottom
    tqdm.write(formatted_msg)