import json
from pathlib import Path
import uvicorn

from fastapi import FastAPI, HTTPException

app = FastAPI()
cars: list[dict] = json.loads(Path("src/cars.json").read_text())

@app.get("/cars")
def list_cars() -> list[dict]:
    """Return a list of all cars."""
    return cars

@app.get("/cars/{car_id}")
def get_car(car_id: int) -> dict:
    """Return a single car by its id, or raise 404 if it doesn't exist."""
    for car in cars:
        if car["id"] == car_id:
            return car
    raise HTTPException(status_code=404, detail="Car not found")

if __name__ == "__main__":
    uvicorn.run('main:app', host='127.0.0.1', port=8080, reload=True)