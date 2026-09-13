import pandas as pd
from pathlib import Path

from data_loader import load
from image_evidence import fill_missing_amounts
from finance_engine import safe_now, earliest_full
from decision_engine import decide
from validator import validate


ROOT = Path(__file__).parent.parent


def run(request_file="requests.csv"):

    data = load()

    # Recover missing amounts using image evidence.
    data["events"] = fill_missing_amounts(
        data["events"],
        data["images"]
    )

    if request_file == "requests.csv":
        requests = data["requests"]

    else:
        requests = pd.read_csv(
            ROOT / "dataset" / request_file
        )

        requests["request_date"] = pd.to_datetime(
            requests["request_date"],
            errors="coerce"
        )

        requests[
            "desired_completion_date"
        ] = pd.to_datetime(
            requests["desired_completion_date"],
            errors="coerce"
        )

    output = []

    for _, req in requests.iterrows():

        user = req["user_id"]
        request_date = req["request_date"]
        amount = float(
            req["requested_amount"]
        )

        safe = safe_now(
            data["events"],
            data["profiles"],
            data["rates"],
            user,
            request_date
        )

        earliest = earliest_full(
            data["events"],
            data["profiles"],
            data["rates"],
            user,
            request_date,
            amount
        )

        result = decide(
            req,
            data,
            safe,
            earliest
        )

        output.append(result)

    output_df = pd.DataFrame(
        output,
        columns=[
            "request_id",
            "amount_safe_to_pay",
            "affordability_status",
            "recommended_payment_method",
            "payment_plan",
            "earliest_date_for_full_payment",
            "spending_changes_needed",
            "decision_explanation",
        ]
    )

    validate(
        output_df,
        requests
    )

    output_df.to_csv(
        ROOT / "output.csv",
        index=False
    )

    print("Created output.csv")


if __name__ == "__main__":
    run()