from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class SuccessResult(BaseModel, Generic[T]):
    success: bool = True
    data: T
    error: str = ""
    debug: dict[str, Any] = Field(default_factory=dict)


class ErrorResult(BaseModel):
    success: bool = False
    data: None = None
    error: str
    debug: dict[str, Any] = Field(default_factory=dict)
