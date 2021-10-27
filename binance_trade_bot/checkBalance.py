from binance_api_manager import BinanceAPIManager
def get_asset_balance(asset, **params):
    """Get current asset balance.

    :param asset: required
    :type asset: str
    :param recvWindow: the number of milliseconds the request is valid for
    :type recvWindow: int

    :returns: dictionary or None if not found

    .. code-block:: python

        {
            "asset": "BTC",
            "free": "4723846.89208129",
            "locked": "0.00000000"
        }

    :raises: BinanceRequestException, BinanceAPIException

    """
    client = BinanceAPIManager()
    res = client.get_account()
    # find asset balance in list of balances
    if "balances" in res:
        for bal in res['balances']:
            if bal['asset'].lower() == asset.lower():
                print(bal)
                return bal
    return None


#  get_asset_balance()
# for item in asset list check balance
x = 10
for i in range(0, x):
    print(i)

