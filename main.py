from benchmark import Benchmark

prompt = """
You are playing a game of Codemaster in the role of the CODEMASTER.
You will receive a list of words on a board, each assigned to a group: <blue | red | assassin>.

Your objective is to help your partner (the Guesser) identify all the "blue" words in as few turns as possible, without them guessing "red" words or the "assassin" word.

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
You must reply with a single tuple containing your clue word and the number of board words it connects to. Your partner will make their guess based on this clue. Count has to be >0.
Return ONLY this strict tuple format: (word, count)

Few-shot examples:
(ocean, 2)
(greek, 1)
    """
promptExplainer = """
    You are playing a game of Codemaster in the role of the GUESSER.
You will receive a list of available words on a board and a clue from your partner (the Codemaster).

Your objective is to guess the hidden "blue" words based on the Codemaster's clues in as few turns as possible, while avoiding "red" words and the "assassin" word.

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
"""

def main():
    benchmark = (
        Benchmark()
        # .addLLM({"modelName": "qwen2.5:14b", "type": "local", "prompts": {"Codemaster": prompt, "Guesser": promptExplainer}})
        .addLLM({"modelName": "llama3.1:70b", "type": "local", "prompts": {"Codemaster": prompt, "Guesser": promptExplainer}})
        .addLLM({"modelName": "llama3.1:70b", "type": "local", "prompts": {"Codemaster": prompt, "Guesser": promptExplainer}})
        .addLLM({"modelName": "llama3.1:70b", "type": "local", "prompts": {"Codemaster": prompt, "Guesser": promptExplainer}})
        # .addLLM({"modelName": "", "type": "debug", "prompts": {"Codemaster": prompt, "Guesser": promptExplainer}})
        .configureGame()
            .setDuration(4)
            .setRefinementStep(2)
            .setGroupConfig({"blue": 1, "red": 1,"assassin": 2})
            .setLanguageConfig({"German": 2, "English": 5})
            .done()
        .build()
    )

    # print(benchmark.summary())

    benchmark.runBenchmarkSet()


if __name__ == "__main__":
    main()