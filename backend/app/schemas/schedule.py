"""Schedule, device and notification schemas (docs/api/openapi.yaml: Reminder, PushToken, Notification)."""
from __future__ import annotations

import re
from datetime import datetime, time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.diet import MealType
from app.schemas.training import Weekday

ReminderType = Literal["meal_reminder", "training_reminder"]
NotificationType = Literal["meal_reminder", "training_reminder", "progress_update", "achievement", "motivational"]
Platform = Literal["android", "ios"]

# Expo push tokens look like ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx] (older: ExpoPushToken[...]).
EXPO_TOKEN = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_\-]{1,200}\]$")


class ReminderInput(BaseModel):
    type: ReminderType
    meal_type: MealType | None = Field(
        default=None, description="Required for meal_reminder, must be null for training_reminder")
    weekdays: Annotated[list[Weekday], Field(min_length=1, max_length=7, json_schema_extra={"uniqueItems": True})]
    time_of_day: time = Field(description="Local time of the user")
    message: str | None = Field(default=None, max_length=200)
    is_enabled: bool = True

    @field_validator("weekdays")
    @classmethod
    def _unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Weekdays must be unique")
        return value

    @field_validator("time_of_day")
    @classmethod
    def _local_time(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("Give the local time of the user without a UTC offset")
        return value

    @field_validator("message")
    @classmethod
    def _no_nul(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("Must not contain a NUL character")
        return value

    @model_validator(mode="after")
    def _meal_type_matches_type(self) -> ReminderInput:
        if self.type == "meal_reminder" and self.meal_type is None:
            raise ValueError("meal_type is required for a meal_reminder")
        if self.type == "training_reminder" and self.meal_type is not None:
            raise ValueError("meal_type must be null for a training_reminder")
        return self


class Reminder(ReminderInput):
    id: int


class PutRemindersRequest(BaseModel):
    reminders: list[ReminderInput]


class PushTokenRequest(BaseModel):
    token: str = Field(description="Expo push token")
    platform: Platform

    @field_validator("token")
    @classmethod
    def _expo_token(cls, value: str) -> str:
        if not EXPO_TOKEN.match(value):
            raise ValueError("Not an Expo push token (ExponentPushToken[...])")
        return value


class PushToken(BaseModel):
    id: int
    token: str
    platform: Platform


class Notification(BaseModel):
    id: int
    type: NotificationType
    title: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict, description='Deep link payload, e.g. {"report_id": 12}')
    created_at: datetime
    read_at: datetime | None = None


class NotificationPage(BaseModel):
    items: list[Notification]
    total: int
    limit: int
    offset: int
