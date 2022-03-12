from Enums.cpuActionEnum import CPUAction
from Enums.stateEnum import State
from Cache.cacheL1 import CacheLine
from Cache.cacheL1 import Cache
from Communication.messaging import Message
from Communication.messaging import MessageType
import time
import logging
from threading import Lock


class CacheController:
    def __init__(self, cache: Cache, logger: logging.Logger):
        self.cache = cache
        self.received_messages_queue = []
        self.send_messages_queue = []
        self.logger = logger
        self.lock = Lock()
        self.messages_received = 0
        self.messages_accepted = 0

    def return_next_send_message(self):
        try:
            return self.send_messages_queue.pop(0)
        except IndexError:
            return None

    def write_request(self, address: int, new_value: str):
        self.lock.acquire()
        state = self.cache.obtain_address_state(address)
        self.transition_by_cpu(state, CPUAction.WRITE, address, new_value)
        self.lock.release()

    def read_request(self, address: int):
        self.lock.acquire()
        state = self.cache.obtain_address_state(address)
        data = self.transition_by_cpu(state, CPUAction.READ, address)
        self.lock.release()
        return data

    def receive_message_from_bus(self, message: Message):
        self.logger.info("Message received from bus; message:" + message.__str__())
        self.logger.info("Accepted msgs: " + str(self.messages_received) + "Received msgs: " + str(self.messages_accepted))
        self.messages_received += 1
        if message.message_type == MessageType.READ_MISS \
                or message.message_type == MessageType.WRITE_MISS:
            self.lock.acquire()
            self.messages_accepted += 1
            self.transition_by_bus(message)
            self.lock.release()
        else:
            self.messages_accepted += 1
            self.received_messages_queue.append(message)

    def transition_by_cpu(self, current_state: State,
                          action: CPUAction, address: int, new_value: str = None):
        self.logger.info("Transition by cpu; current state: " + str(current_state))
        if current_state == State.I:
            return self.transition_by_cpu_from_I(action, address, new_value)
        elif current_state == State.S:
            return self.transition_by_cpu_from_S(action, address, new_value)
        elif current_state == State.E:
            return self.transition_by_cpu_from_E(action, address, new_value)
        elif current_state == State.O:
            return self.transition_by_cpu_from_O(action, address, new_value)
        elif current_state == State.M:
            return self.transition_by_cpu_from_M(action, address, new_value)

    def transition_by_cpu_from_I(self, action: CPUAction, address: int, new_value: str = None):
        block = self.cache.select_block_to_overwrite(address)
        if action == CPUAction.READ:
            self.broadcast_read_miss(address)
            sharers_found = self.are_there_sharers(address)
            if not sharers_found:
                self.ask_data_from_memory(address)
                data = self.read_memory_response_from_bus(address)
                next_state = State.E
                self.overwrite_existing_block(block, address, data, next_state)
            else:
                data = self.read_data_from_bus(address)
                if data is None:
                    self.logger.info("aqui hay que hacer que se meta al primer caso del if no sharers found")
                next_state = State.S
                self.overwrite_existing_block(block, address, data, next_state)
            return block.data
        elif action == CPUAction.WRITE:
            self.broadcast_write_miss(address)
            next_state = State.M
            self.overwrite_existing_block(block, address, new_value, next_state)
        self.logger.info("Transition by cpu; next_state: " + str(next_state))

    def transition_by_cpu_from_S(self, action: CPUAction, address: int, new_value: str = None):
        if action == CPUAction.READ:
            next_state = State.S
            return self.cache.read_and_update_state(address, next_state)
        elif action == CPUAction.WRITE:
            self.broadcast_write_miss(address)
            next_state = State.M
            self.cache.write(address, new_value, next_state)
        self.logger.info("Transition by cpu; next_state: " + str(next_state))

    def transition_by_cpu_from_E(self, action: CPUAction, address: int, new_value: str = None):
        if action == CPUAction.READ:
            next_state = State.E
            return self.cache.read_and_update_state(address, next_state)
        elif action == CPUAction.WRITE:
            next_state = State.M
            self.cache.write(address, new_value, next_state)
        self.logger.info("Transition by cpu; next_state: " + str(next_state))

    def transition_by_cpu_from_O(self, action: CPUAction, address: int, new_value: str = None):
        if action == CPUAction.READ:
            next_state = State.O
            return self.cache.read_and_update_state(address, next_state)
        elif action == CPUAction.WRITE:
            next_state = State.M
            self.broadcast_write_miss(address)
            self.cache.write(address, new_value, next_state)
        self.logger.info("Transition by cpu; next_state: " + str(next_state))

    def transition_by_cpu_from_M(self, action: CPUAction, address: int, new_value: str = None):
        if action == CPUAction.READ:
            next_state = State.M
            return self.cache.read_and_update_state(address, next_state)
        elif action == CPUAction.WRITE:
            next_state = State.M
            self.cache.write(address, new_value, next_state)
        self.logger.info("Transition by cpu; next_state: " + str(next_state))

    def transition_by_bus(self, message: Message):
        current_state = self.cache.obtain_address_state(message.address)
        self.logger.info("Transition by bus ; current state: " + str(current_state))
        if current_state == State.I:
            self.logger.info("Transition by bus; next_state: " + str(State.I))
            pass
        elif current_state == State.S:
            return self.transition_by_bus_from_S(message)
        elif current_state == State.E:
            return self.transition_by_bus_from_E(message)
        elif current_state == State.O:
            return self.transition_by_bus_from_O_and_M(message)
        elif current_state == State.M:
            return self.transition_by_bus_from_O_and_M(message)

    def transition_by_bus_from_S(self, message: Message):
        if message.message_type == MessageType.READ_MISS:
            next_state = State.S
            self.cache.write_state(message.address, next_state)
            self.return_shared_to_bus(message.address, message.origin)
        elif message.message_type == MessageType.WRITE_MISS:
            next_state = State.I
            self.cache.write_state(message.address, next_state)
        self.logger.info("Transition by bus; next_state: " + str(next_state))

    def transition_by_bus_from_E(self, message: Message):
        if message.message_type == MessageType.READ_MISS:
            next_state = State.S
            self.cache.write_state(message.address, next_state)
            self.return_shared_to_bus(message.address, message.origin)
            self.supply_data_to_bus(message.address, self.cache.read(message.address), message.origin)
        elif message.message_type == MessageType.WRITE_MISS:
            next_state = State.I
            self.cache.write_state(message.address, next_state)
        self.logger.info("Transition by bus; next_state: " + str(next_state))

    def transition_by_bus_from_O_and_M(self, message: Message):
        if message.message_type == MessageType.READ_MISS:
            next_state = State.O
            self.cache.write_state(message.address, next_state)
            self.return_shared_to_bus(message.address, message.origin)
            self.supply_data_to_bus(message.address, self.cache.read(message.address), message.origin)
        elif message.message_type == MessageType.WRITE_MISS:
            next_state = State.I
            self.cache.write_state(message.address, next_state)

        self.logger.info("Transition by bus; next_state: " + str(next_state))

    def evict(self, line: CacheLine):
        self.logger.info("Evicting; block number: " + str(line.block_number) + " address: " + str(line.address))
        current_state = line.state
        if current_state == State.I:
            line.set_state(State.I)
        elif current_state == State.S:
            line.set_state(State.I)
        elif current_state == State.E:
            line.set_state(State.I)
        elif current_state == State.O:
            self.ask_write_back(line.address, line.data)
            line.set_state(State.I)
        elif current_state == State.M:
            self.ask_write_back(line.address, line.data)
            line.set_state(State.I)

    def broadcast_read_miss(self, address: int):
        self.send_message_to_bus(MessageType.READ_MISS, address)

    def broadcast_write_miss(self, address: int):
        self.send_message_to_bus(MessageType.WRITE_MISS, address)

    def ask_data_from_memory(self, address: int):
        self.send_message_to_bus(MessageType.REQUEST_FROM_MEMORY, address)

    def ask_write_back(self, address: int, new_value: str):
        self.send_message_to_bus(MessageType.WRITE_BACK, address, data=new_value)

    def are_there_sharers(self, address: int):
        message = self.await_message_from_bus(MessageType.SHARED_RESPONSE, address)
        if message is not None:
            return True
        else:
            return False

    def return_shared_to_bus(self, address: int, destination: int):
        self.send_message_to_bus(MessageType.SHARED_RESPONSE, address, destination=destination)

    def supply_data_to_bus(self, address: int, data: str, destination: int):
        self.send_message_to_bus(MessageType.DATA_RESPONSE, address, data=data, destination=destination)

    def overwrite_existing_block(self, block: CacheLine, address: int, data: str, state: State):
        self.evict(block)
        self.cache.overwrite_block(block, address, data, state)

    def read_data_from_bus(self, address: int):
        message = self.await_message_from_bus(MessageType.DATA_RESPONSE, address)
        if message is not None:
            return message.data
        else:
            self.logger.error("No data was received from the caches")
            return None

    def read_memory_response_from_bus(self, address: int):
        message = self.await_message_from_bus(MessageType.DATA_RESPONSE, address, max_time=30)
        if message is not None:
            return message.data
        else:
            self.logger.error("The memory didn't respond")
            return None


    # TODO: Adjust time
    def await_message_from_bus(self, message_type: MessageType,
                               address: int, max_time: int = 10) -> Message | None:
        start = time.time()
        while time.time() - start < max_time:
            for i in range(len(self.received_messages_queue)):
                message = self.received_messages_queue[i]
                if message.message_type == message_type and message.address == address:
                    self.received_messages_queue.pop(i)
                    return message
        return None

    def send_message_to_bus(self, message_type: MessageType, address: int, destination=None, data=None):
        message = Message(message_type, self.cache.cache_number, destination=destination, address=address, data=data)
        self.logger.info("Message sent to bus; message: " + message.__str__())
        self.send_messages_queue.append(message)
