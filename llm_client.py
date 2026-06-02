import os
import json
import base64
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

load_dotenv()


class BaseLLMClient(ABC):
    _LOG_FILE = "api_requests.jsonl"

    def _log(self, provider: str, model: str, temperature: float, messages: list,
             response: str, duration: float, json_mode: bool):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "json_mode": json_mode,
            "duration_seconds": round(duration, 3),
            "request": _sanitize_messages(messages),
            "response": response,
        }
        with open(self._LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

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
            "temperature": self.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        response = await self.client.chat.completions.create(**kwargs)
        result = response.choices[0].message.content
        self._log("azure", self.deployment_name, self.temperature, messages, result,
                  time.perf_counter() - t0, json_mode)
        return result


class AnthropicClient(BaseLLMClient):
    def __init__(self, model_name: str, temperature: float):
        import anthropic
        self.model_name = model_name
        self.temperature = temperature
        self.client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def generate_response(self, messages: list, json_mode: bool = False) -> str:
        system_parts = []
        filtered = []
        for msg in messages:
            if msg["role"] == "system":
                content = msg["content"]
                system_parts.append(content if isinstance(content, str) else _extract_text(content))
            else:
                filtered.append(_convert_for_anthropic(msg))

        system = "\n\n".join(system_parts) if system_parts else None
        if json_mode:
            json_inst = "Yanıtını yalnızca geçerli JSON olarak ver. JSON nesnesi dışında hiçbir metin ekleme."
            system = f"{system}\n\n{json_inst}" if system else json_inst

        kwargs = {
            "model": self.model_name,
            "messages": filtered,
            "temperature": self.temperature,
            "max_tokens": 4096,
        }
        if system:
            kwargs["system"] = system

        t0 = time.perf_counter()
        response = await self.client.messages.create(**kwargs)
        result = response.content[0].text
        self._log("anthropic", self.model_name, self.temperature, messages, result,
                  time.perf_counter() - t0, json_mode)
        return result


class GeminiClient(BaseLLMClient):
    def __init__(self, model_name: str, temperature: float):
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self._genai = genai
        self.model_name = model_name
        self.temperature = temperature

    async def generate_response(self, messages: list, json_mode: bool = False) -> str:
        system_parts = []
        non_system = []
        for msg in messages:
            if msg["role"] == "system":
                content = msg["content"]
                system_parts.append(content if isinstance(content, str) else _extract_text(content))
            else:
                non_system.append(msg)

        system_instruction = "\n\n".join(system_parts) if system_parts else None
        if json_mode:
            json_inst = "Yanıtını yalnızca geçerli JSON olarak ver. JSON nesnesi dışında hiçbir metin ekleme."
            system_instruction = f"{system_instruction}\n\n{json_inst}" if system_instruction else json_inst

        gemini_messages = []
        for msg in non_system:
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_messages.append({"role": role, "parts": _build_gemini_parts(msg["content"])})

        history = gemini_messages[:-1]
        last_parts = gemini_messages[-1]["parts"] if gemini_messages else [{"text": ""}]

        gen_config = self._genai.types.GenerationConfig(temperature=self.temperature)
        model = self._genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=gen_config,
            system_instruction=system_instruction,
        )
        chat = model.start_chat(history=history)

        t0 = time.perf_counter()
        response = await chat.send_message_async(last_parts)
        result = response.text
        self._log("gemini", self.model_name, self.temperature, messages, result,
                  time.perf_counter() - t0, json_mode)
        return result


# --- Yardımcı fonksiyonlar ---

def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(b["text"] for b in content if b.get("type") == "text")


def _convert_for_anthropic(msg: dict) -> dict:
    content = msg["content"]
    if isinstance(content, str):
        return {"role": msg["role"], "content": content}
    parts = []
    for block in content:
        if block["type"] == "text":
            parts.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image_url":
            url = block["image_url"]["url"]
            if url.startswith("data:"):
                header, data = url.split(";base64,", 1)
                media_type = header.split("data:")[1]
                parts.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })
    return {"role": msg["role"], "content": parts}


def _build_gemini_parts(content) -> list:
    if isinstance(content, str):
        return [{"text": content}]
    parts = []
    for block in content:
        if block["type"] == "text":
            parts.append({"text": block["text"]})
        elif block["type"] == "image_url":
            url = block["image_url"]["url"]
            if url.startswith("data:"):
                header, data = url.split(";base64,", 1)
                media_type = header.split("data:")[1]
                parts.append({"inline_data": {"mime_type": media_type, "data": data}})
    return parts


def _sanitize_messages(messages: list) -> list:
    """Log dosyasını şişirmemek için base64 görsel verisini kırpar."""
    result = []
    for msg in messages:
        content = msg["content"]
        if isinstance(content, list):
            sanitized = []
            for block in content:
                if block.get("type") == "image_url":
                    sanitized.append({"type": "image_url", "image_url": {"url": "[BASE64_IMAGE]"}})
                elif block.get("type") == "image":
                    sanitized.append({"type": "image", "source": {"type": "base64", "data": "[TRUNCATED]"}})
                else:
                    sanitized.append(block)
            result.append({**msg, "content": sanitized})
        else:
            result.append(msg)
    return result


class LLMClientFactory:
    @staticmethod
    def create_client(provider: str, deployment_name: str, temperature: float) -> BaseLLMClient:
        p = provider.lower()
        if p == "azure":
            return AzureOpenAIClient(deployment_name, temperature)
        elif p == "anthropic":
            return AnthropicClient(deployment_name, temperature)
        elif p == "gemini":
            return GeminiClient(deployment_name, temperature)
        else:
            raise ValueError(
                f"Desteklenmeyen sağlayıcı: '{provider}'. "
                f"Desteklenenler: 'azure', 'anthropic', 'gemini'."
            )


def encode_image_to_base64(image_path: str) -> str:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Görsel bulunamadı: {image_path}")
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower()
    mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
    return f"data:{mime_type};base64,{encoded_string}"
