import logging

from app.config import Settings
from app.train import train_and_register

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

settings = Settings()
run_id = train_and_register(settings)
print(f"Training complete. MLflow run: {run_id}")
