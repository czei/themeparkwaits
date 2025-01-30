from src.ErrorHandler import ErrorHandler
import src.theme_park_api

logger = ErrorHandler("error_log")

# Shopify API credentials
API_KEY = "9fe1553756fbcd7fec77adc00e62aca4"  # Replace with your Shopify app's API key
API_SECRET = "b55a2d0f4bb7b48025fd9cbff72df0ec"  # Replace with your Shopify app's API secret
REDIRECT_URI = "https://cff86f-7.myshopify.com"  # Replace with your redirect URL
SCOPES = "read_products,read_orders"  # Define the necessary scopes for your app
SHOP_NAME = "7cff86f-"

import json
from adafruit_datetime import datetime

def is_subscription_active(requests, customer_email):
    """
    Fetches and processes Shopify data based on a provided customer email. It communicates with the Shopify API
    to retrieve customer details and associated subscription orders, parses the subscription renewal date,
    and validates the subscription status.

    :param requests: Requests session or similar library instance to handle HTTP connections.
    :type requests: object
    :param customer_email: The email address of the customer for querying Shopify.
    :type customer_email: str
    :return: A boolean indicating whether the subscription is valid based on the renewal date.
    :rtype: bool
    """
    url = "https://cff86f-7.myshopify.com/admin/api/2025-01/graphql.json"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "CircuitPython/8.1.0",
        "X-shopify-access-token": "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"
    }

    # Get customer ID from the email
    get_by_email_query = get_customer_query(customer_email)

    try:
        # Make the POST request
        # print("Sending request to Shopify...")
        response = requests.post(url, headers=headers, json={"query": get_by_email_query})

        # Check the response
        if response.status_code == 200:
            # print("Response received:")
            # print(response.json())

            # Create a query that searchers for orders associated with
            # the customer ID
            order_query = create_order_query(response.json())
            response = requests.post(url, headers=headers, json={"query": order_query})
            # print(response.json())
            sub_renewal_date = parse_order_date(response.json())
            # print(f"sub_renewal_date = {sub_renewal_date}")
            # print(f"Now is: {datetime.now()}")
            return valid_subscription(sub_renewal_date, datetime.now())
        else:
            logger.debug(f"HTTP Error code connecting to Shopify: {response.status_code}")
    except Exception as e:
        logger.error(e, "Error connecting to Shopify...")

def parse_order_date(json_string):
    """
    Parses the processed date from the input JSON string.

    Args:
        json_string (str): JSON string containing order details.

    Returns:
        datetime: The processed date as a datetime object.
    """
    try:
        order_date_str = json_string['data']['customer']['lastOrder']['createdAt']
        # print(f"Parsed date: {order_date_str}")
        order_date = datetime.fromisoformat(order_date_str[:10])
        return order_date
    except (KeyError, ValueError, TypeError) as e:
        print(f"Error parsing the date: {e}")
        return None

def valid_subscription(subscription_date, current_date):
    grandfathered_date = datetime(2025, 1, 15)
    if subscription_date < grandfathered_date:
        logger.debug("Subscription is grandfathered")
        return True

    num_days = (current_date - subscription_date).days

    if abs(num_days) < 30 :
        return True
    else:
        return False

def parse_form_params(settings, form_params):
    params = form_params.split("&")
    for param in params:
        name_value = param.split("=")
        if name_value[0] == "email":
            settings.settings["email"] = src.theme_park_api.url_decode(name_value[1])
            print(f"Email = {src.theme_park_api.url_decode(name_value[1])}")

def get_customer_query(customer_email):
    get_email_query = "query GetCustomerByEmail {"
    get_email_query += "customers(first: 1, query: \"email:"
    get_email_query += f"{customer_email}\")"
    get_email_query += """{
    edges {
      node {
        id
        email
      }
    }
  }
}
    """
    return get_email_query

# Use Customer ID in JSON to create a query for the orders
# associated with that ID.
def create_order_query(customer_json):

    customer_id = customer_json['data']['customers']['edges'][0]['node']['id']
    query = "query GetLastOrder {\n"
    query += "customer(id: \""
    query += f"{customer_id}"
    query += "\") {"
    query += """
    lastOrder {
      id
      name
      createdAt
      totalPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }
    }
  }
}
    """
    return query

# # Run the function
# subscription_status = fetch_shopify_data()
# if subscription_status is True:
#     print(" Valid subscription")
# else:
#     print ("invalid subscription")
