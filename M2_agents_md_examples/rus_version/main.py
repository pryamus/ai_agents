"""REST API for viewing and managing a collection of cars."""

import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

CARS_FILE = Path(__file__).resolve().parent / "cars.json"

app = FastAPI()


class CarIn(BaseModel):
    """Payload for creating a car without the server-assigned id."""

    make: str
    model: str
    year: int
    horsepower: int
    engine_cc: int = Field(ge=0)
    transmission: str


def _load_cars() -> list[dict]:
    """Load the collection of cars from the data file.

    Returns:
        A list of car records, each containing all fields.
    """
    with CARS_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def _save_cars(cars: list[dict]) -> None:
    """Persist the collection of cars to the data file.

    Args:
        cars: A list of car records to write.
    """
    with CARS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(cars, handle, indent=2, ensure_ascii=False)


cars: list[dict] = _load_cars()


@app.get("/cars")
def list_cars() -> list[dict]:
    """Return all stored cars.

    Returns:
        A list of car records, each containing all fields.
    """
    return cars


@app.get("/cars/{car_id}")
def get_car(car_id: int) -> dict:
    """Return a single car by its unique id.

    Args:
        car_id: Unique numeric identifier of the car.

    Returns:
        The car record matching the given id.

    Raises:
        HTTPException: If no car with the given id exists.
    """
    for car in cars:
        if car["id"] == car_id:
            return car
    raise HTTPException(status_code=404, detail="Car not found")


@app.post("/cars", status_code=201)
def create_car(car: CarIn) -> dict:
    """Create a new car and assign it a server-generated id.

    Args:
        car: Payload of the new car without an id field.

    Returns:
        The created car record containing all fields and the assigned id.
    """
    new_car = car.model_dump()
    new_car["id"] = max((entry["id"] for entry in cars), default=0) + 1
    cars.append(new_car)
    _save_cars(cars)
    return new_car


@app.delete("/cars/{car_id}")
def delete_car(car_id: int) -> dict:
    """Delete a car by its unique id.

    Args:
        car_id: Unique numeric identifier of the car to delete.

    Returns:
        The deleted car record.

    Raises:
        HTTPException: If no car with the given id exists.
    """
    for index, car in enumerate(cars):
        if car["id"] == car_id:
            removed = cars.pop(index)
            _save_cars(cars)
            return removed
    raise HTTPException(status_code=404, detail="Car not found")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
