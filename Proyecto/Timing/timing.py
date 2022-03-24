import time


class Timing:
    def __init__(self, base_timing: float = 1):
        self.base_timing = base_timing
        self.execute_timing = self.base_timing
        self.memory_timing = self.base_timing*14
        self.cache_timing = self.base_timing
        self.max_bus_data_timing = self.base_timing*7
        self.infinite_timing = 1000

    def cache_wait(self):
        time.sleep(self.cache_timing)

    def memory_wait(self):
        time.sleep(self.memory_timing)

    def execute_wait(self):
        time.sleep(self.execute_timing)
