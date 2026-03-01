from benchmark import Benchmark

prompt = """CODEMASTER:
    You are playing a game of Codemaster in the role of codemaster.
    You will get a list of words and their group: <blue|red|assasin>
        Perform a single move of the game, by replying with a single tuple.
    
    Rules
    - Your partner has to guess the blue words based of your clue
    - Every correctly guessed word is +1 points.
    - If your partner guesses a red word it results in -1 point.
    - If your partner gusses an assasin word, you loose the game.
    
    The goal is to guess all the blue words in a minumum amount of turns, while not picking a red word and never picking an assasin word.
    
    Your output to your partner is in this tuple format: (word, count)
    Return only this structure.
    
    word: Your clue word to your partner. 
    count: The amount of words connected to the clue.
    Your partner is going to make it's guess based of this clue.
    
    Constraints:
    - word has to be an English word
    - Is not allowed to be the same word stam as any word on the board
    
    Fex shot example:
    (sky, 2), (greek, 1)
    """
promptExplainer = """GUESSER:
    You are playing a game of Codemaster in the role of guesser.
    You will get a list of words.
    Perform a single move of the game, by replying with a single output: <word|no guess>
    
    Rules
    - You have to guess the blue words based of your clue
    - Every correctly guessed word is +1 points.
    - If you guesse a red word it results in -1 point.
    - If you guesse an assasin word, you loose the game.
    
    The goal is to guess all the blue words in a minumum amount of turns, while not picking a red word and never picking an assasin word.
    
    If you want to guess a word, output only a string this: [word]
    The word has to be exactly the word of the board.
    
    If you dont want to guess anything, output only this: [no guess]
    """

def main():
    benchmark = (
        Benchmark()
        .addLLM({"modelName": "gpt", "type": "local", "prompts": {"Codemaster": prompt, "Guesser": promptExplainer}})
        # .addLLM({"modelName": "gpt4", "type": "local", "prompt": prompt})
        .configureGame()
            .setGameSize(16)
            .setLanguageConfig({"German": 2, "English": 5})
            .done()
        .build()
    )

    # print(benchmark.summary())

    benchmark.runBenchmarkSet()


if __name__ == "__main__":
    main()