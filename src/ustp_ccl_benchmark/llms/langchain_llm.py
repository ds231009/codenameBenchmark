from langchain_openai import ChatOpenAI
from deepeval.models import DeepEvalBaseLLM

class LangchainLLM(DeepEvalBaseLLM):
    """
    A custom wrapper to connect DeepEval to your local lab endpoints
    using LangChain's ChatOpenAI implementation.
    """
    def __init__(self, model_name: str, base_url: str, api_key: str):
        self.model_name = model_name
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0.7,
            api_key=api_key,
            base_url=base_url,
        )

    def load_model(self):
        return self.llm

    def generate(self, prompt: str) -> str:
        res = self.llm.invoke(prompt)
        return res.content

    async def a_generate(self, prompt: str) -> str:
        res = await self.llm.ainvoke(prompt)
        return res.content

    def get_model_name(self):
        return self.model_name