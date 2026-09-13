import pandas as pd

events = pd.read_csv("dataset/financial_events.csv")

users = [
    "user_02",
    "user_05",
    "user_07",
    "user_10",
    "user_17",
    "user_20",
    "user_22",
    "user_25",
]

e = events[events["user_id"].isin(users)].copy()

e["event_date"] = pd.to_datetime(
    e["event_date"],
    errors="coerce"
)

e["settlement_date"] = pd.to_datetime(
    e["settlement_date"],
    errors="coerce"
)

e = e.sort_values(
    ["user_id", "category", "event_date"]
)

for user in users:

    print("\n")
    print("=" * 100)
    print("USER:", user)
    print("=" * 100)

    x = e[e["user_id"] == user]

    print(
        x[
            [
                "event_id",
                "event_type",
                "description",
                "category",
                "direction",
                "amount",
                "currency",
                "event_date",
                "settlement_date",
                "status",
                "flexibility",
                "minimum_allowed_amount",
            ]
        ].to_string(index=False)
    )