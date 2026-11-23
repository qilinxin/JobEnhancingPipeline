"""Load versioned workflow defaults independently of the working directory."""
from pathlib import Path
import tomllib

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config/workflow.toml"
with CONFIG_PATH.open("rb") as config_file:
    SETTINGS = tomllib.load(config_file)
