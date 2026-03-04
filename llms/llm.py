from ollama import chat
from ollama import ChatResponse

from colorama import Fore, Style, init
init(autoreset=True)

def log(colorVariable, *args, **kwargs):
    colorMap = {
        "Guesser": Fore.GREEN,
        "Codemaster": Fore.LIGHTCYAN_EX,
    }
    print(
        colorMap[colorVariable]
        + " "
        + f"[{colorVariable}] "
        + "     "
        + ", ".join(map(str, (*args, *kwargs.values())))
        + Style.RESET_ALL
    )

class LLM():
    def __init__(self, config, role):
        self.modelName = config["modelName"]
        self.type = config["type"]
        self.role = role
        self.prompt = config["prompts"][role]
        
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
        
        if self.type == "local":
            response: ChatResponse = chat(model=self.modelName, messages=msgs)
            return response.message.content
        elif self.type == "debug":
            response = input("\nDebug LLM Input: ")
            return response
        
        return "No valid LLM Type"
            
    def summary(self):
        return {
            "name": self.modelName,
            "type": self.type,
            "prompt": self.prompt,
            "final_strategy": self.strategy_refinement # Good to save in your JSON!
        }