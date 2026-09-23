import csv
import random
from datetime import date, timedelta

random.seed(42)

countries = ["India", "US", "UK", "Singapore"]
platforms = ["Web", "iOS", "Android"]
customer_types = ["New", "Returning"]
payment_methods = ["Card", "UPI", "Wallet"]

rows = []

start_date = date(2026, 9, 1)

for i in range(1000):
    day = start_date + timedelta(days=random.randint(0, 20))
    country = random.choice(countries)
    platform = random.choice(platforms)
    customer_type = random.choice(customer_types)
    payment_method = random.choice(payment_methods)

    sessions = random.randint(50, 300)

    # Normal conversion rate
    conversion_rate = 0.12

    # Create our hidden problem:
    # Android + New users + UPI deteriorates after Sept 14
    if (
        day >= date(2026, 9, 15)
        and platform == "Android"
        and customer_type == "New"
        and payment_method == "UPI"
    ):
        conversion_rate = 0.05

    conversions = int(sessions * conversion_rate)

    # Normal payment failure rate
    failure_rate = 0.02

    # Hidden payment failure spike
    if (
        day >= date(2026, 9, 15)
        and platform == "Android"
        and customer_type == "New"
        and payment_method == "UPI"
    ):
        failure_rate = 0.08

    payment_failures = int(sessions * failure_rate)

    rows.append([
        day,
        country,
        platform,
        customer_type,
        payment_method,
        sessions,
        conversions,
        payment_failures
    ])

with open("trace_data.csv", "w", newline="") as file:
    writer = csv.writer(file)

    writer.writerow([
        "date",
        "country",
        "platform",
        "customer_type",
        "payment_method",
        "sessions",
        "conversions",
        "payment_failures"
    ])

    writer.writerows(rows)

print("Created trace_data.csv with", len(rows), "rows.")
