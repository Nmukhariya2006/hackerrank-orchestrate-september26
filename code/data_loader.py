import pandas as pd
from pathlib import Path


ROOT = Path(__file__).parent.parent
DATA = ROOT / "dataset"


def load():
    files = {
        "events": "financial_events.csv",
        "profiles": "financial_profiles.csv",
        "requests": "requests.csv",
        "options": "request_payment_options.csv",
        "messages": "messages.csv",
        "images": "images.csv",
        "rates": "exchange_rates.csv",
    }

    data = {}

    for key, filename in files.items():
        data[key] = pd.read_csv(DATA / filename)

    date_columns = {
        "events": ["event_date", "settlement_date"],
        "requests": ["request_date", "desired_completion_date"],
        "options": ["first_payment_date"],
        "messages": ["sent_at"],
        "rates": ["rate_date"],
    }

    for name, columns in date_columns.items():
        for column in columns:
            if column in data[name].columns:
                data[name][column] = pd.to_datetime(
                    data[name][column],
                    errors="coerce"
                )

    return data