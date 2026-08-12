"""
Tests for classification module.
"""
import unittest
import tempfile
import pathlib
from datetime import datetime

from roy_classify import Classifier, FileInfo, Category, create_classifier


class TestClassifier(unittest.TestCase):
    """Test file classification."""
    
    def setUp(self):
        """Set up test config."""
        self.config = {
            'classification': {
                'extensions': {
                    'documents': ['.pdf', '.doc', '.txt'],
                    'images': ['.png', '.jpg', '.jpeg'],
                    'videos': ['.mp4', '.mov'],
                    'archives': ['.zip', '.tar', '.gz'],
                    'installers': ['.dmg', '.pkg'],
                    'code': ['.py', '.js', '.ts'],
                },
                'screenshot_patterns': [
                    'Screenshot * at *.png',
                    'Screen Shot * at *.png',
                ],
                'confidence_threshold': 0.7,
                'work_terms': ['work', 'company'],
            },
            'travel': {
                'enabled': True,
                'known_destinations': ['Croatia', 'Norway', 'Spain'],
                'confidence_threshold': 0.8,
            },
            'target_structure': {
                'desktop': ['Inbox', 'Current Projects', 'Temporary'],
                'downloads': ['Documents', 'Images', 'Videos', 'Archives', 'Installers', 'Code', 'Data', 'NeedsReview'],
                'documents': ['Personal', 'Finance', 'Travel', 'Certificates', 'CV-Career', 'Projects', 'NeedsReview'],
                'pictures': ['Screenshots', 'Travel', 'Personal', 'NeedsReview'],
                'movies': ['Travel', 'Insta360', 'GoPro', 'Exports', 'NeedsReview'],
            }
        }
        self.classifier = create_classifier(self.config)
    
    def test_screenshot_detection(self):
        """Test screenshot filename detection."""
        self.assertTrue(self.classifier.is_screenshot("Screenshot 2026-08-12 at 15.24.12.png"))
        self.assertTrue(self.classifier.is_screenshot("Screen Shot 2026-08-12 at 15.24.12.png"))
        self.assertTrue(self.classifier.is_screenshot("Screenshot 2026-01-01 at 12.00.00.png"))
        self.assertFalse(self.classifier.is_screenshot("photo.png"))
        self.assertFalse(self.classifier.is_screenshot("document.pdf"))

    def test_finder_alias_named_like_screenshot_needs_review(self):
        info = FileInfo(
            path=pathlib.Path('/tmp/Screenshot 2026-08-12 at 15.24.12 alias'),
            filename='Screenshot 2026-08-12 at 15.24.12 alias', extension='',
            file_type='MacOS Alias file')
        result = self.classifier.classify(info)
        self.assertEqual(result.category, Category.NEEDS_REVIEW)
        self.assertTrue(result.needs_review)
        self.assertIn('alias', result.reason.lower())
    
    def test_screenshot_date_extraction(self):
        """Test date extraction from screenshot filename."""
        dt = self.classifier.extract_screenshot_date("Screenshot 2026-08-12 at 15.24.12.png")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 12)
        self.assertEqual(dt.hour, 15)
        self.assertEqual(dt.minute, 24)
        self.assertEqual(dt.second, 12)
        
        dt2 = self.classifier.extract_screenshot_date("Screen Shot 2025-12-25 at 09.30.00.png")
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2.year, 2025)
        self.assertEqual(dt2.month, 12)
        self.assertEqual(dt2.day, 25)
    
    def test_extension_classification(self):
        """Test classification by extension."""
        cat, conf = self.classifier.classify_by_extension('.pdf')
        self.assertEqual(cat, 'documents')
        self.assertEqual(conf, 0.9)
        
        cat, conf = self.classifier.classify_by_extension('.png')
        self.assertEqual(cat, 'images')
        
        cat, conf = self.classifier.classify_by_extension('.mp4')
        self.assertEqual(cat, 'videos')
        
        cat, conf = self.classifier.classify_by_extension('.xyz')
        self.assertIsNone(cat)
    
    def test_filename_classification(self):
        """Test classification by filename."""
        cat, conf, reason = self.classifier.classify_by_filename("invoice_2024.pdf")
        self.assertEqual(cat, 'finance')
        
        cat, conf, reason = self.classifier.classify_by_filename("boarding_pass.pdf")
        self.assertEqual(cat, 'travel')
        
        cat, conf, reason = self.classifier.classify_by_filename("certificate.pdf")
        self.assertEqual(cat, 'certificates')
        
        cat, conf, reason = self.classifier.classify_by_filename("resume.pdf")
        self.assertEqual(cat, 'cv_career')
    
    def test_travel_destination_detection(self):
        """Test travel destination detection."""
        dest, conf = self.classifier.detect_travel_destination("Croatia_2024.jpg", pathlib.Path("/Users/test/Pictures/Croatia_2024.jpg"))
        self.assertEqual(dest, "Croatia")
        self.assertGreaterEqual(conf, 0.8)
        
        dest, conf = self.classifier.detect_travel_destination("norway_trip.mp4", pathlib.Path("/Users/test/Movies/norway_trip.mp4"))
        self.assertEqual(dest, "Norway")
    
    def test_full_classification(self):
        """Test full file classification."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test screenshot
            screenshot = pathlib.Path(tmpdir) / "Screenshot 2026-08-12 at 15.24.12.png"
            screenshot.write_text("fake")
            
            file_info = FileInfo(
                path=screenshot,
                filename=screenshot.name,
                extension='.png',
                mime_type='image/png',
                size=100,
                created=datetime.now(),
                modified=datetime.now(),
            )
            
            file_info = self.classifier.classify(file_info)
            self.assertEqual(file_info.category, Category.SCREENSHOTS)
            self.assertGreaterEqual(file_info.confidence, 0.9)
            
            # Test PDF document
            pdf = pathlib.Path(tmpdir) / "document.pdf"
            pdf.write_text("fake")
            
            file_info2 = FileInfo(
                path=pdf,
                filename=pdf.name,
                extension='.pdf',
                mime_type='application/pdf',
                size=1000,
                created=datetime.now(),
                modified=datetime.now(),
            )
            
            file_info2 = self.classifier.classify(file_info2)
            self.assertEqual(file_info2.category, Category.DOCUMENTS)
    
    def test_propose_destination_screenshot(self):
        """Test destination proposal for screenshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            screenshot = pathlib.Path(tmpdir) / "Screenshot 2026-08-12 at 15.24.12.png"
            screenshot.write_text("fake")
            
            file_info = FileInfo(
                path=screenshot,
                filename=screenshot.name,
                extension='.png',
                mime_type='image/png',
                size=100,
                created=datetime(2026, 8, 12, 15, 24, 12),
                modified=datetime.now(),
                category=Category.SCREENSHOTS,
                confidence=0.95,
            )
            
            dest = self.classifier.propose_destination(file_info, self.config)
            self.assertIsNotNone(dest)
            self.assertIn("Screenshots", str(dest))
            self.assertIn("2026", str(dest))
            self.assertIn("2026-08", str(dest))
    
    def test_low_confidence_needs_review(self):
        """Test that low confidence files go to NeedsReview."""
        with tempfile.TemporaryDirectory() as tmpdir:
            unknown = pathlib.Path(tmpdir) / "random_file.xyz"
            unknown.write_text("fake")
            
            file_info = FileInfo(
                path=unknown,
                filename=unknown.name,
                extension='.xyz',
                mime_type=None,
                size=100,
                created=datetime.now(),
                modified=datetime.now(),
            )
            
            file_info = self.classifier.classify(file_info)
            self.assertEqual(file_info.category, Category.NEEDS_REVIEW)
            self.assertTrue(file_info.needs_review)


if __name__ == '__main__':
    unittest.main()
