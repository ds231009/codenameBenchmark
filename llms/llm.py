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
        
        # 1. Initialize the memory with the System prompt
        self.history = [
            {'role': 'system', 'content': self.prompt}
        ]
        
    def getLLMResponse(self, board, clue=None):
        # 2. Build the message for the current turn
        turn_content = f"This is the current board as an array: {board}"
        
        if self.role == "Guesser" and clue:
            turn_content = f"This is your partners clue: {clue}. The word hints towards the word your partner wants you to guess. The number implies the number of words the clue is meant for\n\n" + turn_content
            
        # 3. Append the user's turn to the history
        self.history.append({
            'role': 'user',
            'content': turn_content
        })
        
        log(self.role, f"Sending {len(self.history)} messages to LLM...")
        
        # 4. Send the ENTIRE history to the model
        response: ChatResponse = chat(model=self.modelName, messages=self.history)
        
        # 5. CRITICAL: Save the model's answer back into the history!
        self.history.append({
            'role': 'assistant',
            'content': response.message.content
        })

        return response.message.content

    def summary(self):
        return {
            "name": self.modelName,
            "type": self.type,
            "prompt": self.prompt,
        }