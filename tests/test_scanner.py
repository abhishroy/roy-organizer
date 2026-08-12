"""
Tests for scanner module.
"""
import unittest
import tempfile
import pathlib
import shutil
from datetime import datetime

from roy_scan import Scanner, create_scanner, ScanStats
from roy_classify import Category


class TestScanner(unittest.TestCase):
    """Test scanner functionality."""
    
    def setUp(self):
        """Set up test config and temp directories."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp_dir.name)
        
        # Create test directory structure
        self.desktop = self.base / "Desktop"
        self.downloads = self.base / "Downloads"
        self.documents = self.base / "Documents"
        self.pictures = self.base / "Pictures"
        self.movies = self.base / "Movies"
        
        for d in [self.desktop, self.downloads, self.documents, self.pictures, self.movies]:
            d.mkdir()
        
        self.config = {
            'scan_paths': [
                str(self.desktop),
                str(self.downloads),
                str(self.documents),
                str(self.pictures),
                str(self.movies),
            ],
            'classification': {
                'extensions': {
                    'documents': ['.pdf', '.txt'],
                    'images': ['.png', '.jpg'],
                    'videos': ['.mp4'],
                    'archives': ['.zip'],
                    'installers': ['.dmg'],
                    'code': ['.py'],
                },
                'screenshot_patterns': [
                    'Screenshot * at *.png',
                ],
                'confidence_threshold': 0.7,
                'work_terms': ['work', 'company'],
            },
            'travel': {
                'enabled': True,
                'known_destinations': ['Croatia'],
                'confidence_threshold': 0.8,
            },
            'target_structure': {
                'desktop': ['Inbox', 'Current Projects', 'Temporary'],
                'downloads': ['Documents', 'Images', 'Videos', 'Archives', 'Installers', 'Code', 'Data', 'NeedsReview'],
                'documents': ['Personal', 'Finance', 'Travel', 'Certificates', 'CV-Career', 'Projects', 'NeedsReview'],
                'pictures': ['Screenshots', 'Travel', 'Personal', 'NeedsReview'],
                'movies': ['Travel', 'Insta360', 'GoPro', 'Exports', 'NeedsReview'],
            },
            'duplicates': {
                'min_size': 1,  # Lower threshold for testing
                'use_hash': True,
            },
            'safety': {
                'protected_paths': [],
                'skip_hidden': True,
                'skip_git_repos': True,
            }
        }
        self.scanner = create_scanner(self.config)
    
    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()
    
    def test_scan_basic(self):
        """Test basic scanning."""
        # Create test files
        (self.desktop / "test.txt").write_text("hello")
        (self.desktop / "image.png").write_text("fake image")
        (self.downloads / "doc.pdf").write_text("fake pdf")
        (self.pictures / "Screenshot 2026-08-12 at 15.24.12.png").write_text("screenshot")
        
        files, stats = self.scanner.scan()
        
        self.assertEqual(stats.total_files, 4)
        self.assertGreaterEqual(stats.by_category.get('Documents', 0), 1)
        self.assertGreaterEqual(stats.by_category.get('Images', 0), 1)
        self.assertGreaterEqual(stats.screenshots, 1)
    
    def test_skip_hidden_files(self):
        """Test that hidden files are skipped."""
        (self.desktop / "visible.txt").write_text("hello")
        (self.desktop / ".hidden").write_text("hidden")
        
        files, stats = self.scanner.scan()
        
        self.assertEqual(stats.total_files, 1)
        self.assertEqual(stats.skipped, 1)
    
    def test_skip_git_repos(self):
        """Test that files in git repos are skipped."""
        repo = self.desktop / "my_project"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / "code.py").write_text("print('hello')")
        
        (self.desktop / "outside.txt").write_text("outside")
        
        files, stats = self.scanner.scan()
        
        self.assertEqual(stats.total_files, 1)
        self.assertEqual(stats.skipped, 1)
    
    def test_work_terms_detection(self):
        """Test work term detection."""
        (self.desktop / "work_document.txt").write_text("work")
        (self.desktop / "personal.txt").write_text("personal")
        
        files, stats = self.scanner.scan()
        
        self.assertEqual(stats.total_files, 1)
        self.assertEqual(stats.work_review, 1)
        self.assertEqual(stats.skipped, 1)
    
    def test_duplicate_detection(self):
        """Test duplicate detection."""
        # Create two identical files with same content and size
        content = "same content for duplicate detection"
        (self.desktop / "file1.txt").write_text(content)
        (self.downloads / "file2.txt").write_text(content)
        
        files, stats = self.scanner.scan()
        
        self.assertGreaterEqual(len(stats.duplicates), 1)
        # Check that one is marked as duplicate
        dup_files = [f for f in files if f.is_duplicate]
        self.assertGreaterEqual(len(dup_files), 1)
    
    def test_screenshot_classification(self):
        """Test screenshot classification."""
        (self.pictures / "Screenshot 2026-08-12 at 15.24.12.png").write_text("screenshot")
        (self.pictures / "photo.jpg").write_text("photo")
        
        files, stats = self.scanner.scan()
        
        screenshots = [f for f in files if f.category == Category.SCREENSHOTS]
        self.assertEqual(len(screenshots), 1)
        self.assertEqual(stats.screenshots, 1)
        
        # Check proposed destination
        ss = screenshots[0]
        self.assertIsNotNone(ss.proposed_destination)
        self.assertIn("Screenshots", str(ss.proposed_destination))
        self.assertIn("2026", str(ss.proposed_destination))
        self.assertIn("2026-08", str(ss.proposed_destination))
    
    def test_largest_files(self):
        """Test largest files tracking."""
        (self.desktop / "small.txt").write_text("x" * 100)
        (self.desktop / "medium.txt").write_text("x" * 10000)
        (self.desktop / "large.txt").write_text("x" * 1000000)
        
        files, stats = self.scanner.scan()
        
        self.assertEqual(len(stats.largest_files), 3)
        self.assertEqual(stats.largest_files[0].filename, "large.txt")
        self.assertEqual(stats.largest_files[1].filename, "medium.txt")
        self.assertEqual(stats.largest_files[2].filename, "small.txt")
    
    def test_scan_stats_structure(self):
        """Test scan stats has all expected fields."""
        (self.desktop / "test.txt").write_text("hello")
        
        files, stats = self.scanner.scan()
        
        self.assertTrue(hasattr(stats, 'total_files'))
        self.assertTrue(hasattr(stats, 'total_size'))
        self.assertTrue(hasattr(stats, 'by_category'))
        self.assertTrue(hasattr(stats, 'by_folder'))
        self.assertTrue(hasattr(stats, 'largest_files'))
        self.assertTrue(hasattr(stats, 'oldest_files'))
        self.assertTrue(hasattr(stats, 'duplicates'))
        self.assertTrue(hasattr(stats, 'screenshots'))
        self.assertTrue(hasattr(stats, 'archives'))
        self.assertTrue(hasattr(stats, 'installers'))
        self.assertTrue(hasattr(stats, 'videos'))
        self.assertTrue(hasattr(stats, 'pdfs'))
        self.assertTrue(hasattr(stats, 'code_folders'))
        self.assertTrue(hasattr(stats, 'unclassified'))
        self.assertTrue(hasattr(stats, 'skipped'))
        self.assertTrue(hasattr(stats, 'needs_review'))
        self.assertTrue(hasattr(stats, 'work_review'))


if __name__ == '__main__':
    unittest.main()
