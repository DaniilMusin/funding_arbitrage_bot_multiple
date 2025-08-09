class OrderBookQueryResult:
    def __init__(self, query_price: float, query_volume: float, result_price: float, result_volume: float):
        self.query_price = query_price
        self.query_volume = query_volume
        self.result_price = result_price
        self.result_volume = result_volume


class ClientOrderBookQueryResult:
    def __init__(self, query_price, query_volume, result_price, result_volume):
        self.query_price = query_price
        self.query_volume = query_volume
        self.result_price = result_price
        self.result_volume = result_volume
