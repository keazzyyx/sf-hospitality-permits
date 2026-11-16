"""Tool plumbing shared by every function tool: Pydantic in/out, Anthropic tool schema, dispatch."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


def _strip_titles(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: _strip_titles(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [_strip_titles(v) for v in schema]
    return schema


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Anthropic `input_schema` for a Pydantic model (top-level object, titles removed)."""
    schema = _strip_titles(model.model_json_schema())
    schema["type"] = "object"
    return schema  # type: ignore[no-any-return]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], Awaitable[BaseModel]]

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": json_schema_for(self.input_model),
        }

    async def run(self, raw_input: dict[str, Any]) -> tuple[str, bool]:
        """Execute with validated input. Returns (tool_result_content, is_error)."""
        try:
            parsed = self.input_model.model_validate(raw_input)
        except ValidationError as exc:
            return json.dumps(
                {"error": "invalid_input", "details": exc.errors(include_url=False)}, default=str
            ), True
        try:
            result = await self.handler(parsed)
        except ToolExecutionError as exc:
            return json.dumps({"error": exc.code, "message": str(exc)}), True
        return result.model_dump_json(), False


class ToolExecutionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
