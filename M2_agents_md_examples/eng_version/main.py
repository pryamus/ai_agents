import json
from pathlib import Path
from typing import Any, cast

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

app = FastAPI()


def _load_cars() -> list[dict[str, Any]]:
    """Load cars data from cars.json."""
    data_path = Path("cars.json")
    content = data_path.read_text()
    loaded = json.loads(content)
    return cast(list[dict[str, Any]], loaded)


cars: list[dict[str, Any]] = _load_cars()


class CarBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    make: str
    model: str
    year: int
    horsepower: int
    engine_cc: int
    transmission: str


class CarCreate(CarBase):
    pass


class CarUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    make: str | None = None
    model: str | None = None
    year: int | None = None
    horsepower: int | None = None
    engine_cc: int | None = None
    transmission: str | None = None


class Car(CarBase):
    id: int


@app.get("/cars")
def list_cars() -> list[dict[str, Any]]:
    """Return a list of all cars."""
    return cars


@app.get("/cars/{car_id}")
def get_car(car_id: int) -> dict[str, Any]:
    """Return a single car by its id, or raise 404 if it doesn't exist."""
    for car in cars:
        if car["id"] == car_id:
            return car
    raise HTTPException(status_code=404, detail="Car not found")


@app.post("/cars", status_code=201)
def create_car(car: CarCreate) -> dict[str, Any]:
    """Create a new car and return it with assigned id."""
    if cars:
        new_id = max(c["id"] for c in cars) + 1
    else:
        new_id = 1
    new_car = Car(id=new_id, **car.model_dump()).model_dump()
    cars.append(new_car)
    return new_car


@app.put("/cars/{car_id}")
def update_car(car_id: int, car: CarCreate) -> dict[str, Any]:
    """Update a car completely, or raise 404 if not found."""
    for i, existing in enumerate(cars):
        if existing["id"] == car_id:
            updated_car = Car(id=car_id, **car.model_dump()).model_dump()
            cars[i] = updated_car
            return updated_car
    raise HTTPException(status_code=404, detail="Car not found")


@app.patch("/cars/{car_id}")
def patch_car(car_id: int, updates: CarUpdate) -> dict[str, Any]:
    """Partially update a car, or raise 404 if not found."""
    for i, existing in enumerate(cars):
        if existing["id"] == car_id:
            update_data = updates.model_dump(exclude_unset=True)
            existing.update(update_data)
            return existing
    raise HTTPException(status_code=404, detail="Car not found")


@app.delete("/cars/{car_id}", status_code=204)
def delete_car(car_id: int) -> None:
    """Delete a car by id, or raise 404 if not found."""
    for i, existing in enumerate(cars):
        if existing["id"] == car_id:
            del cars[i]
            return
    raise HTTPException(status_code=404, detail="Car not found")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
