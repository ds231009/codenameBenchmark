from ollama import chat
from ollama import ChatResponse

class LLM():
    def __init__(self, config, role):
        self.modelName = config["modelName"]
        self.type = config["type"]
        self.role = role
        self.prompt = config["prompts"][role]
        
        
    def getLLMResponse(self, board, clue=None):
        message = createMessage(self.prompt, board, self.role, clue)
        response: ChatResponse = chat(model='qwen2.5:14b', messages=message)
        return response.message.content

    def summary(self):
        return {
            "name": self.modelName,
            "type": self.type,
            "prompt": self.prompt,
        }


 
def createMessage(prompt, board, role, clue):
    messageContent = []
    messageContent.append({
            'role': 'system',
            'content': prompt,
        })
    
    if role == "Guesser":
        messageContent.append({
                'role': 'user',
                'content': f"This is your partners clue: {clue}. The word hints towards the word your partner wants you to guess. The number implies the number of words the clue is meant for",
            })
    
    messageContent.append({
        'role': 'user',
        'content': f"This is the current board as an array: {board}",
    })
    
    print(role, board)
    
    return messageContent