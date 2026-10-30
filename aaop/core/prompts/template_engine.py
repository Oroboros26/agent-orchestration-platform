import logging
from typing import Any

import tiktoken
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class PromptTemplate:
    def __init__(self, templates_dir: str = "prompts/templates"):
        self.env = Environment(loader=FileSystemLoader(templates_dir))
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def render(
        self,
        template_name: str,
        variables: dict[str, Any],
        max_tokens: int = 8000,
    ) -> str:
        template = self.env.get_template(template_name)
        rendered = template.render(**variables)

        tokens = self.tokenizer.encode(rendered)
        if len(tokens) > max_tokens:
            rendered = self.tokenizer.decode(tokens[:max_tokens])
            logger.warning(
                f"Prompt truncated: {len(tokens)} → {max_tokens} tokens "
                f"(template={template_name})"
            )
        return rendered

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def create_few_shot(
        self,
        examples: list[dict[str, str]],
        max_examples: int = 3,
    ) -> str:
        out = ""
        for i, ex in enumerate(examples[:max_examples]):
            out += f"\nExample {i + 1}:\nInput: {ex['input']}\nOutput: {ex['output']}\n"
        return out
