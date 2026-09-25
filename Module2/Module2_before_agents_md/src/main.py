import json
from pathlib import Path
import uvicorn

from fastapi import FastAPI, HTTPException, Response

app = FastAPI()
cars: list[dict] = json.loads(Path("src/cars.json").read_text())

@app.get("/cars")
def list_cars() -> list[dict]:
    """Return a list of all cars."""
    return cars

@app.post("/cars", status_code=201)
def create_car(payload: dict) -> dict:
    """Create a new car with an auto-assigned id and return it."""
    required_keys = ("make", "model", "year", "horsepower", "engine_cc", "transmission")
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")
    for key in ("year", "horsepower", "engine_cc"):
        if not isinstance(payload[key], int) or isinstance(payload[key], bool):
            raise HTTPException(status_code=400, detail=f"Field '{key}' must be an integer")
    new_car = {key: payload[key] for key in required_keys}
    new_car["id"] = max((existing["id"] for existing in cars), default=0) + 1
    cars.append(new_car)
    return new_car

@app.get("/cars/{car_id}")
def get_car(car_id: int) -> dict:
    """Return a single car by its id, or raise 404 if it doesn't exist."""
    for car in cars:
        if car["id"] == car_id:
            return car
    raise HTTPException(status_code=404, detail="Car not found")

@app.delete("/cars/{car_id}", status_code=204)
def delete_car(car_id: int) -> Response:
    """Delete a car by its id, or raise 404 if it doesn't exist."""
    for index, car in enumerate(cars):
        if car["id"] == car_id:
            cars.pop(index)
            return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Car not found")

if __name__ == "__main__":
    uvicorn.run('main:app', host='127.0.0.1', port=8080, reload=True)