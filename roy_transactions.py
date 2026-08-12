"""
ROY Organizer - Transaction Module
Handles file moves, logging, and undo functionality.
"""
import os
import pathlib
import json
import shutil
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum


class Operation(Enum):
    """Transaction operation types."""
    MOVE = "move"
    RENAME = "rename"
    CREATE_DIR = "create_dir"


@dataclass
class Transaction:
    """A single file operation transaction."""
    timestamp: str
    operation: str
    source: str
    destination: str
    size: int
    checksum: Optional[str] = None
    reason: str = ""
    batch_id: Optional[str] = None
    reversed: bool = False
    reversed_at: Optional[str] = None
    
    def to_jsonl(self) -> str:
        """Convert to JSONL line."""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_jsonl(cls, line: str) -> 'Transaction':
        """Create from JSONL line."""
        data = json.loads(line)
        return cls(**data)


class TransactionLog:
    """Manages the transaction log."""
    
    def __init__(self, log_path: pathlib.Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._transactions: List[Transaction] = []
        self._load()
    
    def _load(self):
        """Load existing transactions from log."""
        if self.log_path.exists():
            try:
                with open(self.log_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._transactions.append(Transaction.from_jsonl(line))
            except Exception as e:
                print(f"Warning: Could not load transaction log: {e}")
    
    def add(self, transaction: Transaction):
        """Add a transaction to the log."""
        self._transactions.append(transaction)
        self._write(transaction)
    
    def _write(self, transaction: Transaction):
        """Write a single transaction to the log."""
        try:
            with open(self.log_path, 'a') as f:
                f.write(transaction.to_jsonl() + '\n')
        except Exception as e:
            print(f"Error writing transaction log: {e}")
    
    def get_batch(self, batch_id: str) -> List[Transaction]:
        """Get all transactions for a batch."""
        return [t for t in self._transactions if t.batch_id == batch_id and not t.reversed]
    
    def get_last_batch(self) -> Optional[str]:
        """Get the most recent batch ID."""
        for t in reversed(self._transactions):
            if not t.reversed and t.batch_id:
                return t.batch_id
        return None
    
    def get_recent_batches(self, count: int) -> List[str]:
        """Get the most recent N batch IDs."""
        batches = []
        seen = set()
        for t in reversed(self._transactions):
            if t.batch_id and t.batch_id not in seen and not t.reversed:
                batches.append(t.batch_id)
                seen.add(t.batch_id)
                if len(batches) >= count:
                    break
        return batches
    
    def mark_reversed(self, batch_id: str):
        """Mark all transactions in a batch as reversed."""
        for t in self._transactions:
            if t.batch_id == batch_id and not t.reversed:
                t.reversed = True
                t.reversed_at = datetime.now().isoformat()
        # Rewrite entire log
        self._rewrite()
    
    def _rewrite(self):
        """Rewrite the entire log file."""
        try:
            with open(self.log_path, 'w') as f:
                for t in self._transactions:
                    f.write(t.to_jsonl() + '\n')
        except Exception as e:
            print(f"Error rewriting transaction log: {e}")
    
    def all_transactions(self) -> List[Transaction]:
        """Get all transactions."""
        return self._transactions.copy()


class FileMover:
    """Handles safe file moving with transaction logging."""
    
    def __init__(self, config: dict, transaction_log: TransactionLog):
        self.config = config
        self.transaction_log = transaction_log
        self.safety_config = config.get('safety', {})
        self.collision_protection = self.safety_config.get('collision_protection', True)
        self.dry_run = False
    
    def set_dry_run(self, dry_run: bool):
        """Set dry run mode."""
        self.dry_run = dry_run
    
    def ensure_dir(self, path: pathlib.Path) -> bool:
        """Ensure directory exists."""
        if self.dry_run:
            return True
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating directory {path}: {e}")
            return False
    
    def move_file(self, source: pathlib.Path, dest: pathlib.Path, 
                  reason: str = "", batch_id: Optional[str] = None) -> bool:
        """Move a file with safety checks and logging."""
        # Check if source exists
        if not source.exists():
            print(f"Source does not exist: {source}")
            return False
        
        # Check for collision
        if self.collision_protection and dest.exists():
            print(f"Destination exists (collision protection): {dest}")
            return False
        
        # Ensure destination directory exists
        if not self.ensure_dir(dest.parent):
            return False
        
        # Get file size
        try:
            size = source.stat().st_size
        except Exception:
            size = 0
        
        # Create transaction
        transaction = Transaction(
            timestamp=datetime.now().isoformat(),
            operation=Operation.MOVE.value,
            source=str(source),
            destination=str(dest),
            size=size,
            reason=reason,
            batch_id=batch_id,
        )
        
        if self.dry_run:
            print(f"  [DRY RUN] MOVE: {source} -> {dest}")
            self.transaction_log.add(transaction)
            return True
        
        # Perform the move
        try:
            shutil.move(str(source), str(dest))
            print(f"  ✓ MOVE: {source} -> {dest}")
            self.transaction_log.add(transaction)
            return True
        except Exception as e:
            print(f"  ✗ MOVE FAILED: {source} -> {dest}: {e}")
            return False
    
    def undo_batch(self, batch_id: str) -> int:
        """Undo all transactions in a batch."""
        transactions = self.transaction_log.get_batch(batch_id)
        if not transactions:
            print(f"No transactions found for batch: {batch_id}")
            return 0
        
        # Reverse order for undo
        transactions.reverse()
        success_count = 0
        
        for txn in transactions:
            if txn.reversed:
                continue
            
            source = pathlib.Path(txn.destination)
            dest = pathlib.Path(txn.source)
            
            # Check if source (now destination) exists
            if not source.exists():
                print(f"  ⊘ Cannot undo: {source} no longer exists")
                continue
            
            # Check if destination (original source) exists - don't overwrite
            if dest.exists():
                print(f"  ⊘ Cannot undo: {dest} already exists (would overwrite)")
                continue
            
            # Ensure destination directory exists
            if not self.ensure_dir(dest.parent):
                continue
            
            if self.dry_run:
                print(f"  [DRY RUN] UNDO: {source} -> {dest}")
                success_count += 1
                continue
            
            try:
                shutil.move(str(source), str(dest))
                print(f"  ✓ UNDO: {source} -> {dest}")
                success_count += 1
            except Exception as e:
                print(f"  ✗ UNDO FAILED: {source} -> {dest}: {e}")
        
        if success_count > 0 and not self.dry_run:
            self.transaction_log.mark_reversed(batch_id)
        
        return success_count
    
    def undo_last_n(self, n: int) -> int:
        """Undo the last N batches."""
        batches = self.transaction_log.get_recent_batches(n)
        total = 0
        for batch_id in batches:
            count = self.undo_batch(batch_id)
            total += count
            print(f"  Undid batch {batch_id}: {count} operations")
        return total


def create_transaction_log(config: dict) -> TransactionLog:
    """Factory function to create a TransactionLog."""
    log_path = pathlib.Path(config.get('logging', {}).get('transaction_log', 'logs/transactions.jsonl'))
    return TransactionLog(log_path)


def create_file_mover(config: dict, transaction_log: TransactionLog) -> FileMover:
    """Factory function to create a FileMover."""
    return FileMover(config, transaction_log)
