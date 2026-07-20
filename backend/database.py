import redis

class RedisManager:
    def __init__(self, host="localhost", port=6379):
        self.pool = redis.ConnectionPool(host=host, port=port, decode_responses=True)
    
    @property
    def client(self):
        return redis.Redis(connection_pool=self.pool)

redis_db = RedisManager()