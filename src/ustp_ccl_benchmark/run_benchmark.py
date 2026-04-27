from .benchmark import Benchmark

CODEMASTER_PROMPT = """
You are playing a game of Codemaster in the role of the CODEMASTER.
You will receive a list of words on a board, each assigned to a group: <blue | red | assassin>.

Your objective is to help your partner (the Guesser) identify all the "blue" words in as few
turns as possible, without them guessing "red" words or the "assassin" word.

### Rules & Scoring:
* Your partner must guess the "blue" words based on the clue you provide.
* +1 point for every correctly guessed "blue" word.
* -1 point if your partner guesses a "red" word.
* GAME OVER (You lose) if your partner guesses the "assassin" word.

### Move Constraints:
* You must provide exactly ONE clue per turn.
* The clue word MUST be a valid English word.
* The clue word MUST NOT share the same word stem as any word currently visible on the board.

### Output Format:
You must reply with a single tuple containing your clue word and the number of board words it
connects to. Your partner will make their guess based on this clue. Count has to be >0.
Return ONLY this strict tuple format: (word, count)

Few-shot examples:
(ocean, 2)
(greek, 1)
""".strip()

GUESSER_PROMPT = """
You are playing a game of Codemaster in the role of the GUESSER.
You will receive a list of available words on a board and a clue from your partner (the Codemaster).

Your objective is to guess the hidden "blue" words based on the Codemaster's clues in as few
turns as possible, while avoiding "red" words and the "assassin" word.

### Rules & Scoring:
* +1 point for every correctly guessed "blue" word.
* -1 point if you guess a "red" word.
* GAME OVER (You lose) if you guess the "assassin" word.

### Move Instructions:
* You must perform a single move by making one guess at a time.
* The word you guess MUST be chosen from the provided board.
* The word MUST be spelled exactly as it appears on the board.
* If you are unsure and want to end your turn, you can choose to pass.

### Output Format:
If you want to guess a word, output ONLY the word enclosed in brackets:
[word]

If you do not want to guess anything, output ONLY this exact string:
[no guess]
""".strip()


def run_benchmark(bench_config: dict, llm_model) -> tuple[float, dict]:
    """
    Build and run a full benchmark simulation.

    Args:
        bench_config:   Arbitrary config dict passed through to the benchmark.
        langchain_llm:  A LangchainLLM (or compatible) instance.
    """
    benchmark = (
        Benchmark()
        .addLLM(llm_model)
        .addPrompts(CODEMASTER_PROMPT, GUESSER_PROMPT)
        .addBenchConfig(bench_config)
        .configureGame()
            .setDuration(4)
            .setRefinementStep(2)
            .setGroupConfig({"blue": 1, "red": 1, "assassin": 2})
            .setLanguageConfig({"German": 2, "English": 5})
            .done()
        .build()
    )

    print(benchmark.summary())
    benchmark.runBenchmarkSet()
    
    final_score, raw_details = benchmark.get_results()
    
    return final_score, raw_details