"""Identifier types whose values must fit the database column (found by the schemathesis run, task B-28).

The contract gives ids no upper limit, but PostgreSQL does: the reference tables (exercises, foods, muscle groups,
allergens, injury types, food categories) use `integer`, the user data tables use `bigint`. A value outside the column
range makes the driver raise, which used to end as HTTP 500. These types reject such a value with a field-level 422
instead. `AfterValidator` leaves the generated OpenAPI untouched, so the schema still equals the contract.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Path, Query
from pydantic import AfterValidator

INT32 = (-(2**31), 2**31 - 1)
INT64 = (-(2**63), 2**63 - 1)


def _fits(bounds: tuple[int, int]):
    low, high = bounds

    def check(value: int) -> int:
        if not low <= value <= high:
            raise ValueError(f"Must be between {low} and {high}")
        return value

    return check


Id32 = Annotated[int, AfterValidator(_fits(INT32))]   # integer columns: reference data
Id64 = Annotated[int, AfterValidator(_fits(INT64))]   # bigint columns: user data
PathId32 = Annotated[int, Path(ge=1), AfterValidator(_fits(INT32))]
PathId64 = Annotated[int, Path(ge=1), AfterValidator(_fits(INT64))]
OffsetQuery = Annotated[int, Query(ge=0), AfterValidator(_fits(INT64))]
