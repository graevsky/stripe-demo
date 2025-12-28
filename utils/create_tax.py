import os
import environ
import stripe


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = environ.Env(
    STRIPE_SECRET_KEY=(str, None),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))
stripe.api_key = env("STRIPE_SECRET_KEY")


def create_tax_rate():
    try:
        tax_rate = stripe.TaxRate.create(
            display_name="VAT",
            percentage=20.0,
            inclusive=False,
            country="NL",
            description="VAT",
        )
        print(f"Tax rate created successfully: {tax_rate.id}")
        return tax_rate
    except stripe.error.StripeError as e:
        print(f"Stripe error: {e.user_message}")
        return None


if __name__ == "__main__":
    create_tax_rate()
