import pandas as pd


COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


STATUSES = {
    "affordable_now",
    "affordable_with_plan",
    "affordable_later",
    "not_affordable",
}


METHODS = {
    "full_payment",
    "partial_payment",
    "installments",
    "wait",
    "not_recommended",
}


def validate(df, requests):

    errors = []

    if list(df.columns) != COLUMNS:
        errors.append("Wrong columns")

    if len(df) != len(requests):
        errors.append("Wrong row count")

    if not df["request_id"].equals(
        requests["request_id"]
    ):
        errors.append(
            "Request order/IDs changed"
        )

    if not df[
        "affordability_status"
    ].isin(STATUSES).all():
        errors.append(
            "Invalid affordability status"
        )

    if not df[
        "recommended_payment_method"
    ].isin(METHODS).all():
        errors.append(
            "Invalid payment method"
        )

    if df[
        "amount_safe_to_pay"
    ].isna().any():
        errors.append(
            "Missing safe amount"
        )

    if errors:
        raise ValueError(
            "; ".join(errors)
        )

    print("Validation passed.")