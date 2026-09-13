import pandas as pd
from datetime import timedelta
from pandas.tseries.offsets import DateOffset


def profile_for(profiles, user_id):
    p = profiles[profiles["user_id"] == user_id]

    if p.empty:
        return None

    return p.iloc[0]


def clean_events(events, user_id):
    e = events[
        events["user_id"] == user_id
    ].copy()

    e["amount"] = pd.to_numeric(
        e["amount"],
        errors="coerce"
    )

    e["event_date"] = pd.to_datetime(
        e["event_date"],
        errors="coerce"
    )

    e["settlement_date"] = pd.to_datetime(
        e["settlement_date"],
        errors="coerce"
    )

    # Actual cash movement happens on settlement date.
    # If settlement date is missing, use event date.
    e["cash_date"] = e["settlement_date"]

    e["cash_date"] = e["cash_date"].fillna(
        e["event_date"]
    )

    e["status"] = (
        e["status"]
        .astype(str)
        .str.lower()
        .str.strip()
    )

    # Failed and cancelled transactions
    # must not affect available cash.
    e = e[
        ~e["status"].isin(
            {
                "failed",
                "cancelled"
            }
        )
    ]

    # Remove duplicate financial records.
    e = e.drop_duplicates(
        subset=[
            "event_id",
            "user_id",
            "event_type",
            "amount",
            "event_date"
        ]
    )

    return e


def valid_cash_event(row):
    status = str(
        row["status"]
    ).lower()

    if status in {
        "failed",
        "cancelled"
    }:
        return False

    if pd.isna(row["amount"]):
        return False

    if pd.isna(row["cash_date"]):
        return False

    return True


def convert_amount(
    amount,
    from_currency,
    to_currency,
    date,
    rates
):
    if pd.isna(amount):
        return None

    from_currency = str(
        from_currency
    ).upper()

    to_currency = str(
        to_currency
    ).upper()

    if from_currency == to_currency:
        return float(amount)

    rates = rates.copy()

    rates["rate_date"] = pd.to_datetime(
        rates["rate_date"],
        errors="coerce"
    )

    rates["from_currency"] = (
        rates["from_currency"]
        .astype(str)
        .str.upper()
    )

    rates["to_currency"] = (
        rates["to_currency"]
        .astype(str)
        .str.upper()
    )

    date = pd.Timestamp(date)

    # Direct conversion
    candidates = rates[
        (rates["from_currency"] == from_currency)
        &
        (rates["to_currency"] == to_currency)
        &
        (rates["rate_date"] <= date)
    ]

    if not candidates.empty:

        row = candidates.sort_values(
            "rate_date"
        ).iloc[-1]

        return (
            float(amount)
            * float(row["rate"])
        )

    # Reverse conversion
    reverse = rates[
        (rates["from_currency"] == to_currency)
        &
        (rates["to_currency"] == from_currency)
        &
        (rates["rate_date"] <= date)
    ]

    if not reverse.empty:

        row = reverse.sort_values(
            "rate_date"
        ).iloc[-1]

        return (
            float(amount)
            / float(row["rate"])
        )

    return None


def cash_amount(
    row,
    profile,
    rates,
    date
):
    return convert_amount(
        row["amount"],
        row["currency"],
        profile["home_currency"],
        date,
        rates
    )

def recurring_series(events: pd.DataFrame) -> list[dict]:
    """
    Detect recurring series using:
    description + category + direction + currency.

    Requires at least 3 occurrences and a consistent
    detected cadence.
    """

    if events.empty or "amount" not in events.columns:
        return []

    e = events[
        events["amount"].notna()
        &
        events["cash_date"].notna()
    ].copy()

    keys = [
        c for c in [
            "description",
            "category",
            "direction",
            "currency"
        ]
        if c in e.columns
    ]

    if not keys:
        return []

    result = []

    for _, group in e.groupby(
        keys,
        dropna=False
    ):

        group = group.sort_values(
            "cash_date"
        )

        if len(group) < 3:
            continue

        dates = list(
            pd.to_datetime(group["cash_date"])
        )

        gaps = [
            (dates[i] - dates[i - 1]).days
            for i in range(1, len(dates))
        ]

        if not gaps:
            continue

        median_gap = sorted(gaps)[
            len(gaps) // 2
        ]

        # Detect recurrence type
        if 6 <= median_gap <= 8:
            recurrence = "weekly"

        elif 9 <= median_gap <= 11:
            recurrence = "ten_day"

        elif 13 <= median_gap <= 15:
            recurrence = "biweekly"

        elif 27 <= median_gap <= 32:
            recurrence = "monthly"

        else:
            continue

        # Check consistency
        if recurrence == "weekly":
            matching = sum(
                6 <= g <= 8
                for g in gaps
            )

        elif recurrence == "ten_day":
            matching = sum(
                9 <= g <= 11
                for g in gaps
            )

        elif recurrence == "biweekly":
            matching = sum(
                13 <= g <= 15
                for g in gaps
            )

        else:
            matching = sum(
                27 <= g <= 32
                for g in gaps
            )

        consistency = (
            matching / len(gaps)
        )

        if consistency < 0.70:
            continue

        row = group.iloc[-1]

        result.append({
            "last_date": dates[-1],
            "recurrence": recurrence,
            "amount": float(
                group["amount"].median()
            ),
            "currency": row.get(
                "currency"
            ),
            "direction": row.get(
                "direction"
            ),
            "category": row.get(
                "category",
                ""
            ),
            "description": row.get(
                "description",
                ""
            ),
        })

    return result
def generate_recurring(
    events: pd.DataFrame,
    request_date,
    end_date
) -> pd.DataFrame:

    rows = []

    request_date = pd.Timestamp(
        request_date
    )

    end_date = pd.Timestamp(
        end_date
    )

    user_id = (
        events.iloc[0].get("user_id")
        if not events.empty
        and "user_id" in events.columns
        else None
    )

    for s in recurring_series(events):

        current = pd.Timestamp(
            s["last_date"]
        )

        while True:

            # Monthly = calendar month
            if s["recurrence"] == "monthly":

                current = (
                    current
                    + DateOffset(months=1)
                )

            elif s["recurrence"] == "weekly":

                current += timedelta(
                    days=7
                )

            elif s["recurrence"] == "ten_day":

                current += timedelta(
                    days=10
                )

            elif s["recurrence"] == "biweekly":

                current += timedelta(
                    days=14
                )

            else:
                break

            if current > end_date:
                break

            if current <= request_date:
                continue

            rows.append({
                "event_id": "generated",
                "user_id": user_id,
                "amount": s["amount"],
                "currency": s["currency"],
                "direction": s["direction"],
                "category": s["category"],
                "description": s["description"],
                "event_date": current,
                "settlement_date": current,
                "cash_date": current,
                "status": "scheduled",
                "flexibility": "fixed",
                "minimum_allowed_amount": None
            })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)
def get_flows(events, user_id, request_date, end_date):

    e = clean_events(
        events,
        user_id
    )

    request_date = pd.Timestamp(request_date)
    end_date = pd.Timestamp(end_date)

    # Real future cash movements
    future = e[
        (e["cash_date"] > request_date)
        &
        (e["cash_date"] <= end_date)
    ].copy()

    # Predicted recurring movements
    generated = generate_recurring(
        e,
        request_date,
        end_date
    )

    if not generated.empty:

        # Prevent generated transactions from duplicating
        # an actual transaction already present in the dataset.
        actual_keys = set()

        for _, row in future.iterrows():
            actual_keys.add((
                pd.Timestamp(row["cash_date"]).date(),
                str(row["direction"]).lower(),
                str(row["category"]).lower(),
                str(row["currency"]).upper(),
                round(float(row["amount"]), 2)
            ))

        keep = []

        for _, row in generated.iterrows():

            key = (
                pd.Timestamp(row["cash_date"]).date(),
                str(row["direction"]).lower(),
                str(row["category"]).lower(),
                str(row["currency"]).upper(),
                round(float(row["amount"]), 2)
            )

            if key not in actual_keys:
                keep.append(row)

        if keep:
            generated = pd.DataFrame(keep)
            future = pd.concat(
                [future, generated],
                ignore_index=True
            )

    if future.empty:
        return future

    if "cash_date" not in future.columns:
        future["cash_date"] = pd.NaT

    future["cash_date"] = future["cash_date"].fillna(
        future["settlement_date"]
    )

    future["cash_date"] = future["cash_date"].fillna(
        future["event_date"]
    )

    return (
        future
        .sort_values("cash_date")
        .reset_index(drop=True)
    )


def apply_flow(
    balance,
    row,
    profile,
    rates,
    date
):
    if not valid_cash_event(row):
        return balance

    value = cash_amount(
        row,
        profile,
        rates,
        date
    )

    if value is None:
        return balance

    direction = str(
        row["direction"]
    ).lower()

    if direction == "credit":

        balance += value

    elif direction == "debit":

        balance -= value

    return balance


def forecast(
    events,
    profiles,
    rates,
    user_id,
    request_date,
    end_date
):
    profile = profile_for(
        profiles,
        user_id
    )

    if profile is None:
        return []

    flows = get_flows(
        events,
        user_id,
        request_date,
        end_date
    )

    balance = float(
        profile[
            "current_available_balance"
        ]
    )

    result = []

    for _, row in flows.iterrows():

        if not valid_cash_event(row):
            continue

        balance = apply_flow(
            balance,
            row,
            profile,
            rates,
            row["cash_date"]
        )

        result.append({
            "date": row["cash_date"],
            "balance": balance,
            "row": row
        })

    return result


def safe_now(
    events,
    profiles,
    rates,
    user_id,
    request_date
):
    profile = profile_for(
        profiles,
        user_id
    )

    if profile is None:
        return 0.0

    minimum = float(
        profile[
            "minimum_balance_to_keep"
        ]
    )

    balance = float(
        profile[
            "current_available_balance"
        ]
    )

    end_date = (
        pd.Timestamp(request_date)
        + timedelta(days=90)
    )

    flows = get_flows(
        events,
        user_id,
        request_date,
        end_date
    )

    # Amount that can be spent immediately
    # while preserving the minimum balance.
    safe = balance - minimum

    if safe < 0:
        safe = 0.0

    future_balance = balance

    for _, row in flows.iterrows():

        future_balance = apply_flow(
            future_balance,
            row,
            profile,
            rates,
            row["cash_date"]
        )

        available = (
            future_balance
            - minimum
        )

        if available < safe:
            safe = available

    return max(
        0.0,
        safe
    )


def earliest_full(
    events,
    profiles,
    rates,
    user_id,
    request_date,
    amount
):
    profile = profile_for(
        profiles,
        user_id
    )

    if profile is None:
        return None

    minimum = float(
        profile[
            "minimum_balance_to_keep"
        ]
    )

    request_date = pd.Timestamp(
        request_date
    )

    end_date = (
        request_date
        + timedelta(days=90)
    )

    flows = get_flows(
        events,
        user_id,
        request_date,
        end_date
    )

    current_balance = float(
        profile[
            "current_available_balance"
        ]
    )

    # Check request date first.
    if can_pay_on_date(
        current_balance,
        flows,
        request_date,
        amount,
        minimum,
        profile,
        rates
    ):
        return request_date

    if flows.empty:
        return None

    dates = sorted(
        set(
            flows["cash_date"]
        )
    )

    for date in dates:

        if date <= request_date:
            continue

        if can_pay_on_date(
            current_balance,
            flows,
            date,
            amount,
            minimum,
            profile,
            rates
        ):
            return date

    return None


def can_pay_on_date(
    starting_balance,
    flows,
    payment_date,
    amount,
    minimum,
    profile,
    rates
):
    payment_date = pd.Timestamp(
        payment_date
    )

    balance = float(
        starting_balance
    )

    # Apply all cash movements up to
    # and including the payment date.
    for _, row in flows.iterrows():

        date = pd.Timestamp(
            row["cash_date"]
        )

        if date > payment_date:
            break

        balance = apply_flow(
            balance,
            row,
            profile,
            rates,
            date
        )

    # Make requested payment.
    balance -= float(
        amount
    )

    # Minimum must remain protected.
    if balance < minimum:
        return False

    # Check remaining 90-day forecast.
    future = flows[
        flows["cash_date"]
        > payment_date
    ]

    for _, row in future.iterrows():

        date = pd.Timestamp(
            row["cash_date"]
        )

        balance = apply_flow(
            balance,
            row,
            profile,
            rates,
            date
        )

        if balance < minimum:
            return False

    return True