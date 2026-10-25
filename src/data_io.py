"""Load shelter-report and inventory CSVs as raw text DataFrames.

Everything is read as strings; type conversion and checks happen in validation.
"""
import pandas as pd

from src.schemas import INVENTORY_COLUMNS, INVENTORY_REQUIRED, SHELTER_COLUMNS, SHELTER_REQUIRED


def _load(path_or_buffer, columns, required):
    df = pd.read_csv(path_or_buffer, dtype=str, keep_default_na=False, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    df = df.apply(lambda col: col.str.strip())
    for col in columns:  # optional columns may be omitted; missing required ones are reported by validation
        if col not in df.columns and col not in required:
            df[col] = ""
    return df


def load_shelter_reports(path_or_buffer):
    return _load(path_or_buffer, SHELTER_COLUMNS, SHELTER_REQUIRED)


def load_inventory(path_or_buffer):
    return _load(path_or_buffer, INVENTORY_COLUMNS, INVENTORY_REQUIRED)
