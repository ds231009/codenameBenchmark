from colorama import Fore, Style, init
init(autoreset=True)
def log(colorVariable, *args, **kwargs):
    colorMap = {
        "Guesser": Fore.GREEN,
        "Codemaster": Fore.LIGHTCYAN_EX,
    }
    print(
        colorMap.get(colorVariable, Fore.WHITE)
        + " "
        + f"[{colorVariable}] "
        + "     "
        + ", ".join(map(str, (*args, *kwargs.values())))
        + Style.RESET_ALL
    )

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


class LLM():
    def __init__(self, base_llm, config, role):
        """
        Initializes the LLM wrapper.
        Usage: model_guesser = LLM(llm_model, config, "Guesser")
        """
        self.base_llm = base_llm
        
        # Dynamically fetch the model name from the wrapper if available
        self.modelName = base_llm.get_model_name() if hasattr(base_llm, 'get_model_name') else config.get("modelName", "Unknown")
        
        self.role = role
        self.prompt = CODEMASTER_PROMPT if role == "Codemaster" else GUESSER_PROMPT
        
        # Initialize strategy attribute
        self.strategy_refinement = ""
        
        # 1. Initialize the memory with the System prompt
        self.clearMemory()
        
    def getLLMResponse(self, board, clue=None, feedback=None):
        # 2. Build the message for the current turn
        turn_content = f"This is the current board as an array: {board}"
        
        if feedback:
            turn_content = f"FEEDBACK FROM LAST TURN: {feedback}\n\n" + turn_content
        
        if self.role == "Guesser" and clue:
            turn_content = f"This is your partners clue: {clue}. The word hints towards the word your partner wants you to guess. The number implies the number of words the clue is meant for\n\n" + turn_content
            
        # 3. Append the user's turn to the history
        self.history.append({
            'role': 'user',
            'content': turn_content
        })
        
        log(self.role, f"Calling {self.role}... {board}")
        response = self.callLLM()
        
        # 5. CRITICAL: Save the model's answer back into the history!
        self.history.append({
            'role': 'assistant',
            'content': response
        })

        return response
    
    def writeRefinement(self, refinement_batch):
        """Generates a continuous learning strategy based on the past batch of games."""
        
        # 1. Format the batch history into a readable transcript
        history_text = ""
        for game in refinement_batch:
            history_text += f"\n--- Game {game['game_index']} ---\n"
            if game['turn_history']:
                history_text += "\n".join(game['turn_history']) + "\n"
            else:
                history_text += "No turns played.\n"

        # 2. The strict prompt for strategy reflection
        reflection_prompt = (
            "You have just completed a batch of Codenames games. Here is the transcript of your clues and your partner's guesses:\n"
            f"{history_text}\n"
            "Analyze your performance. Did the Guesser misunderstand your clues? Did they hit penalty words?\n"
            "Based on this analysis, formulate a short list of strategic rules for yourself to improve your future performance.\n\n"
            "CRITICAL RULES FOR THIS REFLECTION:\n"
            "1. Focus ONLY on abstract strategy (e.g., risk management, specificity of clues, clue counts, word types).\n"
            "2. DO NOT mention any specific words from the previous games, as the next boards will have completely different words.\n"
            "3. Output ONLY the strategic guidelines. This exact output will become your system instructions for the next rounds."
        )

        # 3. Create a temporary conversation just for this reflection
        temp_history = [
            {'role': 'system', 'content': "You are an expert AI analyzing your past gameplay to build a better strategy."},
            {'role': 'user', 'content': reflection_prompt}
        ]
        
        log(self.role, "Reflecting on batch to generate new strategy...")
        
        # Pass the temp_history explicitly to callLLM
        new_strategy = self.callLLM(messages=temp_history)
        
        # 4. Save the new strategy so clearMemory can inject it
        self.strategy_refinement = new_strategy
        log(self.role, f"New Strategy generated:\n{new_strategy}")
        
        return new_strategy

    def clearMemory(self):
        """Wipes history but injects the learned strategy into the base prompt."""
        system_content = self.prompt
        
        # If we have learned a strategy from writeRefinement, append it!
        if self.strategy_refinement:
            system_content += "\n\n### YOUR CONTINUOUS LEARNING STRATEGY (Follow these tips strictly):\n"
            system_content += self.strategy_refinement
            
        self.history = [
            {'role': 'system', 'content': system_content}
        ]
        log(self.role, "Memory cleared. Base prompt and strategy loaded.")

    def callLLM(self, messages=None):
        # Allow passing custom messages for the reflection step, otherwise use history
        msgs = messages if messages is not None else self.history
        
        # Translate our dict history into LangChain's native tuple format
        langchain_msgs = []
        for m in msgs:
            if m['role'] == 'system':
                langchain_msgs.append(("system", m['content']))
            elif m['role'] == 'assistant':
                langchain_msgs.append(("ai", m['content']))
            else:
                langchain_msgs.append(("human", m['content']))
        
        # Attempt 1: If the wrapper exposes load_model() (like your OllamaLLM)
        # This is ideal because it passes the structured history directly to LangChain
        if hasattr(self.base_llm, 'load_model'):
            response = self.base_llm.load_model().invoke(langchain_msgs)
            return response.content
            
        # Attempt 2: Fallback to the generic DeepEval generate() method
        elif hasattr(self.base_llm, 'generate'):
            # Flatten the structured history into a single string
            flat_prompt = "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in msgs])
            return self.base_llm.generate(flat_prompt)
        
        # Attempt 3: Debug mode bypass
        elif getattr(self.base_llm, 'type', None) == "debug":
            return input(f"\nDebug LLM Input for {self.role}: ")
            
        return "No valid LLM configuration found."
            
    def summary(self):
        return {
            "name": self.modelName,
            "role": self.role,
            "prompt": self.prompt,
            "final_strategy": self.strategy_refinement 
        }