def get_all_coins_info(self, **params):
    return self._request_margin_api('get', 'capital/config/getall', True, data=params)