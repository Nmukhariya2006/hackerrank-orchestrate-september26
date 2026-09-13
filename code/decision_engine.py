from datetime import timedelta
import pandas as pd


def pretty_date(date):
    return f"{date.day} {date.strftime('%B %Y')}"


def amount_text(value):
    value = float(value)

    if value.is_integer():
        return f"{value:,.0f}"

    return f"{value:,.2f}"


def plan_amount_text(value):
    value = float(value)

    if value.is_integer():
        return f"{value:.0f}"

    return f"{value:.2f}"


def allowed(profile, method):
    if profile is None:
        return False

    try:
        methods = str(
            profile["payment_methods_user_will_consider"]
        ).lower()
    except (KeyError, TypeError):
        return False

    allowed_methods = {
        x.strip()
        for x in methods.split("|")
    }

    return method.lower() in allowed_methods

def option_for(options, request_id, method):
    x = options[
        (options["request_id"] == request_id)
        &
        (
            options["payment_method"]
            .astype(str)
            .str.lower()
            == method.lower()
        )
    ]

    if x.empty:
        return None

    return x.iloc[0]


# ============================================================
# SPENDING CHANGES
# ============================================================

def find_spending_changes(req, data, safe, earliest):
    """
    Find up to 3 spending changes that may make the purchase possible.

    Allowed changes:
        stop:event_id
        reduce_to:event_id:new_amount

    Only recurring flexible expenses are considered.
    """

    profile = data["profiles"]

    user_id = req["user_id"]
    request_date = req["request_date"]
    requested_amount = float(req["requested_amount"])

    profile_rows = profile[
        profile["user_id"] == user_id
    ]

    if profile_rows.empty:
        return "none"

    p = profile_rows.iloc[0]

    reducible_categories = {
        x.strip().lower()
        for x in str(
            p.get(
                "expense_categories_user_is_willing_to_reduce",
                ""
            )
        ).split("|")
        if x.strip()
    }

    stoppable_categories = {
        x.strip().lower()
        for x in str(
            p.get(
                "expense_categories_user_is_willing_to_stop",
                ""
            )
        ).split("|")
        if x.strip()
    }

    if not reducible_categories and not stoppable_categories:
        return "none"

    events = data["events"].copy()

    if events.empty:
        return "none"

    # --------------------------------------------------------
    # Make sure dates exist
    # --------------------------------------------------------

    if "cash_date" not in events.columns:

        if "settlement_date" in events.columns:
            events["cash_date"] = pd.to_datetime(
                events["settlement_date"],
                errors="coerce"
            )

        else:
            events["cash_date"] = pd.to_datetime(
                events["event_date"],
                errors="coerce"
            )

    else:
        events["cash_date"] = pd.to_datetime(
            events["cash_date"],
            errors="coerce"
        )

    # --------------------------------------------------------
    # Basic filtering
    # --------------------------------------------------------

    events = events[
        events["user_id"] == user_id
    ].copy()

    if events.empty:
        return "none"

    events = events[
        events["cash_date"].notna()
    ].copy()

    events = events[
        events["cash_date"] > request_date
    ].copy()

    # Only expenses
    if "direction" in events.columns:
        events = events[
            events["direction"]
            .astype(str)
            .str.lower()
            .isin(["out", "debit", "expense"])
        ].copy()

    # Remove failed/cancelled events
    if "status" in events.columns:

        bad_status = {
            "failed",
            "cancelled",
            "canceled"
        }

        events = events[
            ~events["status"]
            .astype(str)
            .str.lower()
            .isin(bad_status)
        ].copy()

    if events.empty:
        return "none"

    # Only flexible expenses
    if "flexibility" in events.columns:

        events = events[
            events["flexibility"]
            .astype(str)
            .str.lower()
            .isin(
                [
                    "flexible",
                    "optional"
                ]
            )
        ].copy()

    if events.empty:
        return "none"

    # --------------------------------------------------------
    # Category filtering
    # --------------------------------------------------------

    events["category_clean"] = (
        events["category"]
        .fillna("")
        .astype(str)
        .str.lower()
        .str.strip()
    )

    allowed_categories = (
        reducible_categories
        | stoppable_categories
    )

    if allowed_categories:

        events = events[
            events["category_clean"].isin(
                allowed_categories
            )
        ].copy()

    if events.empty:
        return "none"

    # --------------------------------------------------------
    # Find recurring expenses
    # --------------------------------------------------------

    candidates = []

    group_columns = [
        "description",
        "category",
        "direction",
        "currency"
    ]

    group_columns = [
        c
        for c in group_columns
        if c in events.columns
    ]

    if not group_columns:
        return "none"

    for _, group in events.groupby(
        group_columns,
        dropna=False
    ):

        group = group.sort_values(
            "cash_date"
        ).copy()

        if len(group) < 2:
            continue

        dates = list(group["cash_date"])

        gaps = [
            (dates[i] - dates[i - 1]).days
            for i in range(1, len(dates))
        ]

        if not gaps:
            continue

        median_gap = sorted(gaps)[
            len(gaps) // 2
        ]

        # Detect cadence
        cadence = None

        if 6 <= median_gap <= 8:
            cadence = 7

        elif 9 <= median_gap <= 11:
            cadence = 10

        elif 13 <= median_gap <= 15:
            cadence = 14

        elif 27 <= median_gap <= 32:
            cadence = 30

        if cadence is None:
            continue

        consistent = sum(
            abs(g - cadence) <= 1
            for g in gaps
        )

        consistency = (
            consistent / len(gaps)
        )

        if consistency < 0.70:
            continue

        # Use the latest FUTURE event.
        latest = group.iloc[-1]

        amount = float(
            latest["amount"]
        )

        if amount <= 0:
            continue

        category = str(
            latest.get(
                "category",
                ""
            )
        ).lower().strip()

        event_id = str(
            latest["event_id"]
        )

        # ----------------------------------------------------
        # STOP candidate
        # ----------------------------------------------------

        if category in stoppable_categories:

            candidates.append(
                {
                    "event_id": event_id,
                    "type": "stop",
                    "amount": amount,
                    "category": category,
                    "date": latest["cash_date"],
                    "currency": latest.get(
                        "currency"
                    ),
                    "description": latest.get(
                        "description",
                        ""
                    )
                }
            )

        # ----------------------------------------------------
        # REDUCE candidate
        # ----------------------------------------------------

        if category in reducible_categories:

            minimum = latest.get(
                "minimum_allowed_amount",
                None
            )

            if pd.notna(minimum):

                minimum = float(minimum)

                if minimum < amount:

                    savings = (
                        amount - minimum
                    )

                    candidates.append(
                        {
                            "event_id": event_id,
                            "type": "reduce",
                            "amount": amount,
                            "minimum": minimum,
                            "savings": savings,
                            "category": category,
                            "date": latest[
                                "cash_date"
                            ],
                            "currency": latest.get(
                                "currency"
                            ),
                            "description": latest.get(
                                "description",
                                ""
                            )
                        }
                    )

    if not candidates:
        return "none"

    # --------------------------------------------------------
    # If already affordable, no spending change needed
    # --------------------------------------------------------

    if safe >= requested_amount:
        return "none"

    # --------------------------------------------------------
    # Rank changes
    #
    # Prefer stopping expenses because it gives the largest
    # possible reduction without inventing a new amount.
    # --------------------------------------------------------

    stop_candidates = [
        c
        for c in candidates
        if c["type"] == "stop"
    ]

    reduce_candidates = [
        c
        for c in candidates
        if c["type"] == "reduce"
    ]

    stop_candidates.sort(
        key=lambda x: x["amount"],
        reverse=True
    )

    reduce_candidates.sort(
        key=lambda x: x["savings"],
        reverse=True
    )

    ordered = (
        stop_candidates
        +
        reduce_candidates
    )

    # --------------------------------------------------------
    # Need additional amount
    # --------------------------------------------------------

    needed = (
        requested_amount
        - float(safe)
    )

    if needed <= 0:
        return "none"

    selected = []
    recovered = 0.0

    # Maximum 3 changes
    for candidate in ordered:

        if len(selected) >= 3:
            break

        if candidate["type"] == "stop":

            recovered += candidate["amount"]

            selected.append(
                f"stop:{candidate['event_id']}"
            )

        else:

            available_reduction = (
                candidate["amount"]
                -
                candidate["minimum"]
            )

            if available_reduction <= 0:
                continue

            # ------------------------------------------------
            # Reduce only as much as required.
            # ------------------------------------------------

            reduction_needed = (
                needed - recovered
            )

            reduction = min(
                available_reduction,
                reduction_needed
            )

            new_amount = (
                candidate["amount"]
                - reduction
            )

            # Respect minimum allowed amount
            new_amount = max(
                new_amount,
                candidate["minimum"]
            )

            new_amount = round(
                new_amount,
                2
            )

            actual_saving = (
                candidate["amount"]
                - new_amount
            )

            if actual_saving <= 0:
                continue

            recovered += actual_saving

            selected.append(
                f"reduce_to:"
                f"{candidate['event_id']}:"
                f"{plan_amount_text(new_amount)}"
            )

        if recovered >= needed:
            break

    # --------------------------------------------------------
    # If changes cannot cover the gap
    # --------------------------------------------------------

    if recovered < needed:
        return "none"

    return selected


# ============================================================
# INSTALLMENT PLAN
# ============================================================

def make_installment_plan(option):

    first = option["first_payment_date"]

    number_of_payments = int(
        option["number_of_payments"]
    )

    frequency = int(
        option["payment_frequency_days"]
    )

    payment_amount = float(
        option["payment_amount"]
    )

    dates = []

    for i in range(
        number_of_payments
    ):

        date = (
            first
            +
            timedelta(
                days=i * frequency
            )
        )

        dates.append(
            f"{date.strftime('%Y-%m-%d')}:"
            f"{plan_amount_text(payment_amount)}"
        )

    return "|".join(dates)


# ============================================================
# MAIN DECISION
# ============================================================

def decide(req, data, safe, earliest):

    profile = data["profiles"]

    request_id = req["request_id"]
    user_id = req["user_id"]

    request_date = req["request_date"]

    amount = float(
        req["requested_amount"]
    )

    currency = str(
        req.get(
            "currency",
            ""
        )
    )

    minimum = float(
        profile[
            profile["user_id"] == user_id
        ].iloc[0]["minimum_balance_to_keep"]
    )

    user_profile = profile[
        profile["user_id"] == user_id
    ]

    if user_profile.empty:
        return None

    user_profile = user_profile.iloc[0]

    # --------------------------------------------------------
    # Safe amount
    # --------------------------------------------------------

    safe = max(
        0.0,
        min(
            float(safe),
            amount
        )
    )

    safe = round(
        safe,
        2
    )

    # --------------------------------------------------------
    # Earliest date
    # --------------------------------------------------------

    earliest_text = ""

    if earliest is not None:

        try:

            earliest_text = (
                earliest.strftime(
                    "%Y-%m-%d"
                )
            )

        except Exception:

            earliest_text = str(
                earliest
            )

    # --------------------------------------------------------
    # Default result
    # --------------------------------------------------------

    result = {
        "request_id": request_id,
        "amount_safe_to_pay": safe,
        "affordability_status": "not_affordable",
        "recommended_payment_method": "not_recommended",
        "payment_plan": "none",
        "earliest_date_for_full_payment": (
            earliest_text
        ),
        "spending_changes_needed": "none",
        "decision_explanation": ""
    }

    # ========================================================
    # 1. AFFORDABLE NOW
    # ========================================================

    if (
        safe >= amount
        and allowed(
            user_profile,
            "full_payment"
        )
    ):

        result[
            "affordability_status"
        ] = "affordable_now"

        result[
            "recommended_payment_method"
        ] = "full_payment"

        result[
            "payment_plan"
        ] = (
            f"{request_date.strftime('%Y-%m-%d')}:"
            f"{plan_amount_text(amount)}"
        )

        result[
            "earliest_date_for_full_payment"
        ] = request_date.strftime(
            "%Y-%m-%d"
        )

        result[
            "decision_explanation"
        ] = (
            f"Pay {currency} "
            f"{amount_text(amount)} today. "
            f"This leaves at least "
            f"{currency} "
            f"{amount_text(minimum)} "
            f"available."
        )

        return result

    # ========================================================
    # 2. PARTIAL PAYMENT
    # ========================================================

    desired_completion = pd.to_datetime(
        req["desired_completion_date"],
        errors="coerce"
    )

    if (
        bool(req.get(
            "allows_partial_payment",
            False
        ))
        and allowed(
            user_profile,
            "partial_payment"
        )
        and safe > 0
        and safe < amount
        and earliest is not None
        and earliest <= desired_completion
    ):

        remaining = round(
            amount - safe,
            2
        )

        result[
            "affordability_status"
        ] = "affordable_with_plan"

        result[
            "recommended_payment_method"
        ] = "partial_payment"

        result[
            "payment_plan"
        ] = (
            f"{request_date.strftime('%Y-%m-%d')}:"
            f"{plan_amount_text(safe)}"
            "|"
            f"{earliest.strftime('%Y-%m-%d')}:"
            f"{plan_amount_text(remaining)}"
        )

        result[
            "decision_explanation"
        ] = (
            f"Pay {currency} "
            f"{amount_text(safe)} now and "
            f"the remaining "
            f"{currency} "
            f"{amount_text(remaining)} "
            f"on {earliest.strftime('%Y-%m-%d')}."
        )

        return result

    # ========================================================
    # 3. INSTALLMENTS
    # ========================================================

    if allowed(
        user_profile,
        "installments"
    ):

        options = data["options"]

        option = option_for(
            options,
            request_id,
            "installments"
        )

        if option is not None:

            max_months = int(
                user_profile[
                    "max_installment_months"
                ]
            )

            number_of_payments = int(
                option[
                    "number_of_payments"
                ]
            )

            if (
                number_of_payments
                <= max_months
            ):

                result[
                    "affordability_status"
                ] = "affordable_with_plan"

                result[
                    "recommended_payment_method"
                ] = "installments"

                result[
                    "payment_plan"
                ] = make_installment_plan(
                    option
                )

                result[
                    "decision_explanation"
                ] = (
                    "Use the available installment "
                    "option while keeping the required "
                    "minimum balance."
                )

                return result

    # ========================================================
    # 4. SPENDING CHANGES
    # ========================================================

    changes = find_spending_changes(
        req,
        data,
        safe,
        earliest
    )

    if (
        safe < amount
        and changes
        and changes != "none"
        and allowed(
            user_profile,
            "full_payment"
        )
    ):

        result[
            "affordability_status"
        ] = "affordable_with_plan"

        result[
            "recommended_payment_method"
        ] = "full_payment"

        # IMPORTANT:
        # find_spending_changes() can return either:
        #
        # "none"
        #
        # OR
        #
        # ["stop:event_1", "reduce_to:event_2:100"]
        #
        # Therefore don't do "|".join("none")
        # because that creates:
        #
        # n|o|n|e

        if isinstance(
            changes,
            str
        ):
            result[
                "spending_changes_needed"
            ] = changes

        else:
            result[
                "spending_changes_needed"
            ] = "|".join(
                changes
            )

        result[
            "payment_plan"
        ] = (
            f"{request_date.strftime('%Y-%m-%d')}:"
            f"{plan_amount_text(amount)}"
        )

        result[
            "decision_explanation"
        ] = (
            "Make the recommended spending changes, "
            f"then pay {currency} "
            f"{amount_text(amount)} today. "
            f"This keeps at least {currency} "
            f"{amount_text(minimum)} available."
        )

        return result

    # ========================================================
    # 5. WAIT
    # ========================================================

    if (
        earliest is not None
        and allowed(
            user_profile,
            "full_payment"
        )
    ):

        result[
            "affordability_status"
        ] = "affordable_later"

        result[
            "recommended_payment_method"
        ] = "wait"

        result[
            "payment_plan"
        ] = (
            f"{earliest.strftime('%Y-%m-%d')}:"
            f"{plan_amount_text(amount)}"
        )

        result[
            "decision_explanation"
        ] = (
            f"Wait until "
            f"{earliest.strftime('%Y-%m-%d')} "
            f"when the full amount can be paid "
            "while preserving the required "
            "minimum balance."
        )

        return result

    # ========================================================
    # 6. NOT AFFORDABLE
    # ========================================================

    result[
        "affordability_status"
    ] = "not_affordable"

    result[
        "recommended_payment_method"
    ] = "not_recommended"

    result[
        "payment_plan"
    ] = "none"

    result[
        "spending_changes_needed"
    ] = "none"

    result[
        "decision_explanation"
    ] = (
        f"The requested amount of "
        f"{currency} "
        f"{amount_text(amount)} "
        "cannot be safely paid under the "
        "available financial constraints."
    )

    return result