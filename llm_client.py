import os
import base64
from abc import ABC, abstractmethod
from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

load_dotenv()

class BaseLLMClient(ABC):
    @abstractmethod
    async def generate_response(self, messages: list, json_mode: bool = False) -> str:
        pass

class AzureOpenAIClient(BaseLLMClient):
    def __init__(self, deployment_name: str, temperature: float):
        self.deployment_name = deployment_name
        self.temperature = temperature
        self.client = AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION")
        )

    async def generate_response(self, messages: list, json_mode: bool = False) -> str:
        kwargs = {
            "model": self.deployment_name,
            "messages": messages,
            "temperature": self.temperature
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
            
        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

class LLMClientFactory:
    @staticmethod
    def create_client(provider: str, deployment_name: str, temperature: float) -> BaseLLMClient:
        if provider.lower() == "azure":
            return AzureOpenAIClient(deployment_name, temperature)
        else:
            raise ValueError(f"Desteklenmeyen sağlayıcı: {provider}. Şimdilik sadece 'azure' destekleniyor.")

def encode_image_to_base64(image_path: str) -> str:
    """Görsel dosyasını okuyup base64 string'e dönüştürür."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Görsel bulunamadı: {image_path}")
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    
    # Dosya uzantısına göre mime-type belirleme
    ext = os.path.splitext(image_path)[1].lower()
    mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
    return f"data:{mime_type};base64,{encoded_string}"