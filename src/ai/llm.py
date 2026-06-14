import json
import os
import time
from pathlib import Path
from typing import Optional, Type, TypeVar

import httpx
from openai import OpenAI
import requests
import instructor
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents
for parent in PROJECT_ROOT:
    if (parent / ".git").exists():
        PROJECT_ROOT = parent
        break

HUMAN_MOCK = False


def get_api_key(key_name):
    env_key = os.environ.get(key_name)
    if env_key:
        return env_key

    key_file = Path(PROJECT_ROOT / f"{key_name.lower()}.txt")
    if key_file.exists():
        return key_file.read_text().strip()

    return None


OPENROUTER_API_KEY = get_api_key("OPENROUTER_API_KEY")
if OPENROUTER_API_KEY:
    os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY
    openrouter_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        timeout=httpx.Timeout(120),
    )
    instructor_client = instructor.from_openai(
        client=openrouter_client, mode=instructor.Mode.JSON
    )
else:
    instructor_client = None


class LLMModel:
    def __init__(self, route: str, input_cost_micros_per_million: float):
        self.route = route
        self.input_cost = input_cost_micros_per_million


CHEAP_LLM = LLMModel(route="google/gemini-2.5-flash", input_cost_micros_per_million=1.5)
STRONG_LLM = LLMModel(
    route="~google/gemini-pro-latest", input_cost_micros_per_million=12.5
)
# STRONG_LLM = CHEAP_LLM


T = TypeVar("T", bound=BaseModel)


def prompt(model: LLMModel, messages: list, return_type: Type[T]) -> Optional[T]:
    response = completion_instructor(
        model=model.route,
        messages=messages,
        response_model=return_type,
    )
    return response


def completion_openrouter(model, messages, timeout=60, num_retries=2):
    if not OPENROUTER_API_KEY:
        raise ValueError("OpenRouter API key not configured.")

    for attempt in range(num_retries + 1):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                },
                data=json.dumps(
                    {
                        "model": model.replace("openrouter/", ""),
                        "messages": messages,
                    }
                ),
                timeout=timeout,
            )
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.RequestException as e:
            print(
                f"OpenRouter API request failed (attempt {attempt + 1}/{num_retries + 1}): {e}"
            )
            if attempt == num_retries:
                raise
            time.sleep(1)
    assert False, "should be unreachable"


def completion_instructor(
    model, messages, response_model: Type[T], timeout=60, num_retries=2
) -> T:
    """Sends a completion request using the instructor-patched OpenAI client."""
    if not instructor_client:
        raise ValueError("Instructor client not initialized. Check OPENAI_API_KEY.")

    response = instructor_client.chat.completions.create(
        # model=model.replace("openrouter/", ""),
        model=model,
        messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        response_model=response_model,
        max_retries=num_retries,
        # extra_body={"provider": {"require_parameters": True}}
    )
    return response


class Conversation:
    def __init__(self):
        self.messages = []
        self.total_cost = 0

    def add_message(self, message: str, role="user", ephemeral=False):
        if role == "system":
            role = "user"
            message = f"SYSTEM: {message}"
        if not message:
            raise ValueError("Message cannot be empty")
        if role not in ["user", "assistant", "system"]:
            raise ValueError(
                f"Invalid role: {role}. Roles are 'user', 'assistant', 'system'"
            )

        self.messages.append({"role": role, "content": message, "ephemeral": ephemeral})
        return self

    def run(
        self, model, should_print=True, response_model: Optional[Type[BaseModel]] = None
    ) -> any:
        response_obj = None

        if HUMAN_MOCK:
            print("\nMOCK MODE: Please provide a response for the following prompt:\n")
            print("Context:")
            for msg in self.messages:
                print(f"{msg['role']}: {msg['content']}\n")
            response_text = input("Enter your response: ")
        else:
            if response_model:
                if not instructor_client:
                    raise ValueError(
                        "Instructor client not available. Cannot use response_model."
                    )

                response_obj = completion_instructor(
                    model=model,
                    messages=self.messages,
                    response_model=response_model,
                    timeout=60,
                    num_retries=0,
                )
                response_text = response_obj.model_dump_json(indent=2)

            else:
                response = completion_openrouter(
                    model=model,
                    messages=self.messages,
                    timeout=60,
                    num_retries=2,
                )
                response_text = response["choices"][0]["message"]["content"]

        self.add_message(response_text, role="assistant")
        if should_print:
            print(f"Bot: {response_text}\n\n")

        self.messages = [
            message for message in self.messages if not message["ephemeral"]
        ]
        if response_obj:
            return response_obj
        return response_text
