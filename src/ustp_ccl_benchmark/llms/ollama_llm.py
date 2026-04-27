from langchain_ollama import ChatOllama
from deepeval.models import DeepEvalBaseLLM

class OllamaLLM(DeepEvalBaseLLM):
    """
    A custom wrapper to connect DeepEval to a local or remote Ollama instance
    using LangChain's ChatOllama implementation.
    """
    def __init__(self, model_name: str, base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        # Note: Ollama usually doesn't require an API key for local use.
        # If your lab proxy requires one, you can add it to headers.
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0.7,
        )

    def load_model(self):
        return self.llm

    def generate(self, prompt: str) -> str:
        """Synchronous generation using LangChain invoke."""
        res = self.llm.invoke(prompt)
        return res.content

    async def a_generate(self, prompt: str) -> str:
        """Asynchronous generation using LangChain ainvoke."""
        res = await self.llm.ainvoke(prompt)
        return res.content

    def get_model_name(self):
        return self.model_name