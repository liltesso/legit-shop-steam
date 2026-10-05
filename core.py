class Problem(Exception):
    def __init__(self, code, status=400, **data):
        self.code, self.status, self.data = code, status, data
