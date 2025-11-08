import requests
import json
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt


def get_markets():

    url = "https://clob.polymarket.com/prices-history"
    interval = "max"
    fidelity = 60*24
    token_id = 21742633143463906290569050155826241533067272736897614950488156847949938836455
    variables = {
        "market": token_id,
        "interval": interval,
        "fidelity": fidelity,
    }
    response = requests.get(url, params=variables)
    response.raise_for_status()
    return response.json()

markets = get_markets()
data = markets["history"]

df = pd.DataFrame(data)
df['timestamp'] = pd.to_datetime(df['t'], unit='s')
df['price'] = df['p']
df = df[['timestamp', 'price']].sort_values('timestamp')


plt.figure(figsize=(12, 6))
plt.plot(df['timestamp'], df['price'], marker='o', linestyle='-')

plt.xlabel('Timestamp')
plt.ylabel('Price')
plt.title('Market Price History')
plt.grid(True)

plt.tight_layout()
plt.show()

