"""Read-only access to the reference data and libraries (B-08, B-09): dictionaries, exercises and foods."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from app.domain.training import Exercise as DomainExercise
from app.domain.training import Injury as DomainInjury


@dataclass
class MuscleGroupRecord:
    id: int
    name: str
    description: str
    image_url: str | None
    body_region: str


@dataclass
class NamedRecord:
    id: int
    name: str
    description: str = ""


@dataclass
class InjuryTypeRecord(NamedRecord):
    avg_healing_time_days: int = 0


@dataclass
class ExerciseRecord:
    id: int
    name: str
    main_muscle_group_id: int
    main_muscle_group_name: str
    difficulty_level: str
    equipment: str
    is_compound: bool
    is_bodyweight: bool
    description: str = ""
    instruction: str = ""
    secondary_muscle_groups: list[tuple[int, str]] = field(default_factory=list)  # detail view only


@dataclass
class FoodRecord:
    id: int
    name: str
    calories_per_100g: Decimal
    protein_per_100g: Decimal
    fat_per_100g: Decimal
    carbs_per_100g: Decimal
    role: str
    default_portion_g: int
    is_vegetarian: bool = False
    is_vegan: bool = False
    min_portion_g: int = 0
    max_portion_g: int = 0
    portion_step_g: int = 0
    categories: list[NamedRecord] = field(default_factory=list)  # detail view only
    allergens: list[NamedRecord] = field(default_factory=list)  # detail view only


@dataclass
class TrainingContext:
    """What FR-A1 needs about the user: level and equipment from the profile (None without a profile) and injuries."""

    experience_level: str | None
    equipment: str | None
    injuries: list[DomainInjury]


class LibraryRepository(Protocol):
    async def muscle_groups(self) -> list[MuscleGroupRecord]: ...
    async def injury_types(self) -> list[InjuryTypeRecord]: ...
    async def allergens(self) -> list[NamedRecord]: ...
    async def food_categories(self) -> list[NamedRecord]: ...

    async def list_exercises(self, *, q: str | None, muscle_group_id: int | None, equipment: str | None,
                             difficulty_level: str | None, limit: int, offset: int) -> tuple[list[ExerciseRecord], int]:
        ...

    async def get_exercise(self, exercise_id: int) -> ExerciseRecord | None: ...
    async def domain_exercises(self) -> list[DomainExercise]: ...
    async def exercises_by_ids(self, ids: list[int]) -> list[ExerciseRecord]: ...
    async def training_context(self, user_id: int) -> TrainingContext: ...

    async def list_foods(self, *, q: str | None, category_id: int | None, role: str | None, limit: int,
                         offset: int) -> tuple[list[FoodRecord], int]: ...

    async def get_food(self, food_id: int) -> FoodRecord | None: ...
