"""
Tests for transaction module.
"""
import unittest
import tempfile
import pathlib
import json
from datetime import datetime

from roy_transactions import (
    Transaction, TransactionLog, FileMover, Operation,
    create_transaction_log, create_file_mover
)


class TestTransaction(unittest.TestCase):
    """Test Transaction dataclass."""
    
    def test_transaction_creation(self):
        """Test creating a transaction."""
        txn = Transaction(
            timestamp=datetime.now().isoformat(),
            operation=Operation.MOVE.value,
            source="/source/file.txt",
            destination="/dest/file.txt",
            size=100,
            reason="test",
            batch_id="batch_1"
        )
        
        self.assertEqual(txn.operation, "move")
        self.assertEqual(txn.source, "/source/file.txt")
        self.assertEqual(txn.destination, "/dest/file.txt")
        self.assertEqual(txn.size, 100)
        self.assertFalse(txn.reversed)
    
    def test_transaction_jsonl(self):
        """Test JSONL serialization."""
        txn = Transaction(
            timestamp="2026-08-12T15:00:00",
            operation="move",
            source="/source/file.txt",
            destination="/dest/file.txt",
            size=100,
            reason="test",
            batch_id="batch_1"
        )
        
        jsonl = txn.to_jsonl()
        parsed = json.loads(jsonl)
        
        self.assertEqual(parsed['operation'], "move")
        self.assertEqual(parsed['source'], "/source/file.txt")
        self.assertEqual(parsed['batch_id'], "batch_1")
    
    def test_transaction_from_jsonl(self):
        """Test parsing from JSONL."""
        line = '{"timestamp": "2026-08-12T15:00:00", "operation": "move", "source": "/source/file.txt", "destination": "/dest/file.txt", "size": 100, "checksum": null, "reason": "test", "batch_id": "batch_1", "reversed": false, "reversed_at": null}'
        
        txn = Transaction.from_jsonl(line)
        
        self.assertEqual(txn.timestamp, "2026-08-12T15:00:00")
        self.assertEqual(txn.operation, "move")
        self.assertEqual(txn.batch_id, "batch_1")
        self.assertFalse(txn.reversed)


class TestTransactionLog(unittest.TestCase):
    """Test TransactionLog."""
    
    def setUp(self):
        """Set up temp log file."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = pathlib.Path(self.temp_dir.name) / "transactions.jsonl"
        self.log = TransactionLog(self.log_path)
    
    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()
    
    def test_add_transaction(self):
        """Test adding a transaction."""
        txn = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file.txt",
            destination="/dest/file.txt",
            size=100,
            reason="test",
            batch_id="batch_1"
        )
        
        self.log.add(txn)
        
        self.assertEqual(len(self.log._transactions), 1)
        self.assertEqual(self.log._transactions[0].batch_id, "batch_1")
    
    def test_get_batch(self):
        """Test getting transactions by batch."""
        txn1 = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file1.txt",
            destination="/dest/file1.txt",
            size=100,
            batch_id="batch_1"
        )
        txn2 = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file2.txt",
            destination="/dest/file2.txt",
            size=200,
            batch_id="batch_1"
        )
        txn3 = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file3.txt",
            destination="/dest/file3.txt",
            size=300,
            batch_id="batch_2"
        )
        
        self.log.add(txn1)
        self.log.add(txn2)
        self.log.add(txn3)
        
        batch1 = self.log.get_batch("batch_1")
        self.assertEqual(len(batch1), 2)
        
        batch2 = self.log.get_batch("batch_2")
        self.assertEqual(len(batch2), 1)
    
    def test_get_last_batch(self):
        """Test getting last batch ID."""
        txn1 = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file1.txt",
            destination="/dest/file1.txt",
            size=100,
            batch_id="batch_1"
        )
        txn2 = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file2.txt",
            destination="/dest/file2.txt",
            size=200,
            batch_id="batch_2"
        )
        
        self.log.add(txn1)
        self.log.add(txn2)
        
        last = self.log.get_last_batch()
        self.assertEqual(last, "batch_2")
    
    def test_mark_reversed(self):
        """Test marking batch as reversed."""
        txn1 = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file1.txt",
            destination="/dest/file1.txt",
            size=100,
            batch_id="batch_1"
        )
        txn2 = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file2.txt",
            destination="/dest/file2.txt",
            size=200,
            batch_id="batch_1"
        )
        
        self.log.add(txn1)
        self.log.add(txn2)
        
        self.log.mark_reversed("batch_1")
        
        self.assertTrue(txn1.reversed)
        self.assertTrue(txn2.reversed)
        self.assertIsNotNone(txn1.reversed_at)
    
    def test_persistence(self):
        """Test that log persists to disk."""
        txn = Transaction(
            timestamp=datetime.now().isoformat(),
            operation="move",
            source="/source/file.txt",
            destination="/dest/file.txt",
            size=100,
            batch_id="batch_1"
        )
        
        self.log.add(txn)
        
        # Create new log instance
        new_log = TransactionLog(self.log_path)
        self.assertEqual(len(new_log._transactions), 1)
        self.assertEqual(new_log._transactions[0].batch_id, "batch_1")


class TestFileMover(unittest.TestCase):
    """Test FileMover."""
    
    def setUp(self):
        """Set up temp directories."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp_dir.name)
        self.source_dir = self.base / "source"
        self.dest_dir = self.base / "dest"
        self.source_dir.mkdir()
        self.dest_dir.mkdir()
        
        self.log_path = self.base / "transactions.jsonl"
        self.log = TransactionLog(self.log_path)
        self.mover = FileMover({}, self.log)
    
    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()
    
    def test_move_file_dry_run(self):
        """Test dry run move."""
        self.mover.set_dry_run(True)
        
        source = self.source_dir / "test.txt"
        source.write_text("hello")
        dest = self.dest_dir / "test.txt"
        
        result = self.mover.move_file(source, dest, "test", "batch_1")
        
        self.assertTrue(result)
        self.assertTrue(source.exists())  # Source should still exist in dry run
        self.assertFalse(dest.exists())  # Dest should not exist in dry run
        
        # Check transaction was logged
        batch = self.log.get_batch("batch_1")
        self.assertEqual(len(batch), 1)
    
    def test_move_file_actual(self):
        """Test actual move."""
        self.mover.set_dry_run(False)
        
        source = self.source_dir / "test.txt"
        source.write_text("hello")
        dest = self.dest_dir / "test.txt"
        
        result = self.mover.move_file(source, dest, "test", "batch_1")
        
        self.assertTrue(result)
        self.assertFalse(source.exists())  # Source should be gone
        self.assertTrue(dest.exists())  # Dest should exist
        self.assertEqual(dest.read_text(), "hello")
        
        # Check transaction was logged
        batch = self.log.get_batch("batch_1")
        self.assertEqual(len(batch), 1)
    
    def test_move_file_collision(self):
        """Test collision protection."""
        self.mover.set_dry_run(False)
        
        source = self.source_dir / "test.txt"
        source.write_text("hello")
        dest = self.dest_dir / "test.txt"
        dest.write_text("existing")
        
        result = self.mover.move_file(source, dest, "test", "batch_1")
        
        self.assertFalse(result)
        self.assertTrue(source.exists())
        self.assertEqual(dest.read_text(), "existing")
    
    def test_undo_batch(self):
        """Test undoing a batch."""
        self.mover.set_dry_run(False)
        
        source = self.source_dir / "test.txt"
        source.write_text("hello")
        dest = self.dest_dir / "test.txt"
        
        # Move
        self.mover.move_file(source, dest, "test", "batch_1")
        self.assertFalse(source.exists())
        self.assertTrue(dest.exists())
        
        # Undo
        count = self.mover.undo_batch("batch_1")
        
        self.assertEqual(count, 1)
        self.assertTrue(source.exists())
        self.assertFalse(dest.exists())
        self.assertEqual(source.read_text(), "hello")
    
    def test_undo_prevents_overwrite(self):
        """Test undo doesn't overwrite existing files."""
        self.mover.set_dry_run(False)
        
        source = self.source_dir / "test.txt"
        source.write_text("hello")
        dest = self.dest_dir / "test.txt"
        
        # Move
        self.mover.move_file(source, dest, "test", "batch_1")
        
        # Create a new file at original location
        source.write_text("new content")
        
        # Try to undo - should fail because source now exists
        count = self.mover.undo_batch("batch_1")
        
        self.assertEqual(count, 0)
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_text(), "hello")
        self.assertEqual(source.read_text(), "new content")


if __name__ == '__main__':
    unittest.main()
