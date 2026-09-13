import pandas as pd
from pathlib import Path

from main import run


ROOT = Path(__file__).parent.parent

FIELDS = [
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def same_value(a, b):

    if pd.isna(a) and pd.isna(b):
        return True

    if (
        isinstance(a, float)
        and isinstance(b, float)
    ):
        return abs(a - b) < 0.01

    return str(a).strip() == str(b).strip()


def main():

    print("=" * 70)
    print("HACKERRANK ORCHESTRATE - SAMPLE TEST")
    print("=" * 70)

    print("\nRunning solution...\n")

    run("sample_requests.csv")

    expected = pd.read_csv(
        ROOT / "dataset" / "sample_requests.csv"
    )

    actual = pd.read_csv(
        ROOT / "output.csv"
    )

    print(
        f"Expected rows : {len(expected)}"
    )

    print(
        f"Actual rows   : {len(actual)}"
    )

    total = 0
    passed = 0

    failed_requests = []

    for i in range(len(expected)):

        request_id = expected.iloc[i][
            "request_id"
        ]

        print("\n" + "-" * 70)
        print(
            f"REQUEST {i + 1}/"
            f"{len(expected)} : "
            f"{request_id}"
        )
        print("-" * 70)

        request_failed = False

        for field in FIELDS:

            total += 1

            exp = expected.iloc[i][field]
            act = actual.iloc[i][field]

            if same_value(exp, act):

                passed += 1

                print(
                    f"[PASS] {field}"
                )

            else:

                request_failed = True

                print(
                    f"[FAIL] {field}"
                )

                print(
                    f"       Expected : {exp}"
                )

                print(
                    f"       Actual   : {act}"
                )

        if request_failed:
            failed_requests.append(
                request_id
            )

    accuracy = (
        passed / total * 100
        if total
        else 0
    )

    print("\n" + "=" * 70)
    print("FINAL TEST SUMMARY")
    print("=" * 70)

    print(
        f"Passed : {passed}/{total}"
    )

    print(
        f"Failed : {total - passed}/{total}"
    )

    print(
        f"Accuracy : {accuracy:.2f}%"
    )

    print(
        f"\nFailed requests : "
        f"{len(failed_requests)}/25"
    )

    if failed_requests:

        print(
            "\nRequests needing attention:"
        )

        for request_id in failed_requests:
            print(
                f" - {request_id}"
            )

    else:

        print(
            "\nAll sample requests passed!"
        )


if __name__ == "__main__":
    main()