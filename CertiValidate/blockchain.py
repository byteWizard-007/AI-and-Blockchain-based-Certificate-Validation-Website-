import hashlib
import json
from time import time

class Block:
    def __init__(self, index, timestamp, data, previous_hash):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        """Calculates the SHA-256 hash of the block."""
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash
        }, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

class Blockchain:
    def __init__(self, storage_file="blockchain.json"):
        self.storage_file = storage_file
        self.chain = []
        self.load_chain()

    def create_genesis_block(self):
        """Generates the first block in the blockchain."""
        genesis_block = Block(0, time(), "Genesis Block - Certificate System Initialization", "0")
        self.chain.append(genesis_block)
        self.save_chain()

    def get_latest_block(self):
        """Returns the most recent block in the chain."""
        return self.chain[-1]

    def add_block(self, data):
        """Adds a new block to the chain securely."""
        previous_block = self.get_latest_block()
        new_block = Block(
            index=previous_block.index + 1,
            timestamp=time(),
            data=data,
            previous_hash=previous_block.hash
        )
        self.chain.append(new_block)
        self.save_chain()
        return new_block

    def is_chain_valid(self):
        """Validates the integrity of the blockchain."""
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = self.chain[i - 1]

            # Re-verify the hash of the block
            if current_block.hash != current_block.calculate_hash():
                return False
            
            # Verify the linkage
            if current_block.previous_hash != previous_block.hash:
                return False
        return True

    def save_chain(self):
        """Persists the blockchain state to a JSON file."""
        try:
            with open(self.storage_file, 'w') as f:
                chain_data = []
                for b in self.chain:
                    chain_data.append({
                        "index": b.index,
                        "timestamp": b.timestamp,
                        "data": b.data,
                        "previous_hash": b.previous_hash,
                        "hash": b.hash
                    })
                json.dump(chain_data, f, indent=4)
        except Exception as e:
            print(f"Error saving chain: {e}")

    def load_chain(self):
        """Loads the blockchain state if it exists, otherwise creates genesis block."""
        try:
            with open(self.storage_file, 'r') as f:
                chain_data = json.load(f)
                for b_data in chain_data:
                    b = Block(b_data['index'], b_data['timestamp'], b_data['data'], b_data['previous_hash'])
                    b.hash = b_data['hash']  # Preserve the exact hash
                    self.chain.append(b)
        except (FileNotFoundError, json.JSONDecodeError):
            self.create_genesis_block()

    def get_all_blocks(self):
        """Returns visualizable properties of all blocks."""
        return [{"index": b.index, "timestamp": b.timestamp, "data": b.data, "previous_hash": b.previous_hash, "hash": b.hash} for b in self.chain]
