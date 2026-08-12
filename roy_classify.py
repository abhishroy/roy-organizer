"""
ROY Organizer - Classification Module
File classification and categorization logic.
"""
import pathlib
import mimetypes
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum


class Category(Enum):
    """File categories."""
    DOCUMENTS = "Documents"
    IMAGES = "Images"
    VIDEOS = "Videos"
    AUDIO = "Audio"
    ARCHIVES = "Archives"
    REPOSITORY_ARCHIVE = "RepositoryArchive"
    INSTALLERS = "Installers"
    CODE = "Code"
    DATA = "Data"
    SCREENSHOTS = "Screenshots"
    TRAVEL = "Travel"
    PERSONAL = "Personal"
    FINANCE = "Finance"
    CERTIFICATES = "Certificates"
    CV_CAREER = "CV-Career"
    PROJECTS = "Projects"
    NEEDS_REVIEW = "NeedsReview"
    WORK_REVIEW_REQUIRED = "WORK_REVIEW_REQUIRED"
    DUPLICATE = "Duplicate"
    LARGE_FILE = "LargeFile"
    UNKNOWN = "Unknown"


@dataclass
class FileInfo:
    """Information about a file."""
    path: pathlib.Path
    filename: str
    extension: str
    mime_type: Optional[str] = None
    file_type: Optional[str] = None
    size: int = 0
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    category: Category = Category.UNKNOWN
    confidence: float = 0.0
    reason: str = ""
    proposed_destination: Optional[pathlib.Path] = None
    is_duplicate: bool = False
    duplicate_of: Optional[pathlib.Path] = None
    hash: Optional[str] = None
    needs_review: bool = False
    work_review: bool = False
    protection_type: Optional[str] = None
    archive_origin: Optional[str] = None
    archive_owner: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'path': str(self.path),
            'filename': self.filename,
            'extension': self.extension,
            'mime_type': self.mime_type,
            'file_type': self.file_type,
            'size': self.size,
            'created': self.created.isoformat() if self.created else None,
            'modified': self.modified.isoformat() if self.modified else None,
            'category': self.category.value,
            'confidence': self.confidence,
            'reason': self.reason,
            'proposed_destination': str(self.proposed_destination) if self.proposed_destination else None,
            'is_duplicate': self.is_duplicate,
            'duplicate_of': str(self.duplicate_of) if self.duplicate_of else None,
            'hash': self.hash,
            'needs_review': self.needs_review,
            'work_review': self.work_review,
            'protection_type': self.protection_type,
            'archive_origin': self.archive_origin,
            'archive_owner': self.archive_owner,
        }


class Classifier:
    """Classifies files into categories."""
    
    def __init__(self, config: dict):
        self.config = config
        self.classification_config = config.get('classification', {})
        self.extensions = self.classification_config.get('extensions', {})
        self.screenshot_patterns = self.classification_config.get('screenshot_patterns', [])
        self.confidence_threshold = self.classification_config.get('confidence_threshold', 0.7)
        self.travel_config = config.get('travel', {})
        self.known_destinations = self.travel_config.get('known_destinations', [])
        self.travel_confidence = self.travel_config.get('confidence_threshold', 0.8)
        
        # Compile screenshot regex patterns - use simpler patterns
        self.screenshot_regexes = [
            re.compile(r'Screenshot \d{4}-\d{2}-\d{2} at \d{2}\.\d{2}\.\d{2}', re.IGNORECASE),
            re.compile(r'Screen Shot \d{4}-\d{2}-\d{2} at \d{2}\.\d{2}\.\d{2}', re.IGNORECASE),
            re.compile(r'Screenshot \d{4}-\d{2}-\d{2}', re.IGNORECASE),
            re.compile(r'Screen Shot \d{4}-\d{2}-\d{2}', re.IGNORECASE),
        ]
        
        # Extension to category mapping
        self.ext_to_category = {}
        for cat, exts in self.extensions.items():
            for ext in exts:
                self.ext_to_category[ext.lower()] = cat
    
    def get_mime_type(self, path: pathlib.Path) -> Optional[str]:
        """Get MIME type of a file using mimetypes (stdlib)."""
        mime, _ = mimetypes.guess_type(str(path))
        return mime
    
    def get_file_type(self, path: pathlib.Path) -> Optional[str]:
        """Get file type description using file command if available."""
        try:
            import subprocess
            result = subprocess.run(
                ['file', '-b', str(path)],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
    
    def is_screenshot(self, filename: str) -> bool:
        """Check if filename matches screenshot patterns."""
        for regex in self.screenshot_regexes:
            if regex.search(filename):
                return True
        return False
    
    def extract_screenshot_date(self, filename: str) -> Optional[datetime]:
        """Extract date from screenshot filename."""
        # Pattern: Screenshot 2026-08-12 at 15.24.12.png
        patterns = [
            r'Screenshot (\d{4}-\d{2}-\d{2}) at (\d{2})\.(\d{2})\.(\d{2})',
            r'Screen Shot (\d{4}-\d{2}-\d{2}) at (\d{2})\.(\d{2})\.(\d{2})',
        ]
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                try:
                    date_str = match.group(1)
                    hour = int(match.group(2))
                    minute = int(match.group(3))
                    second = int(match.group(4))
                    return datetime.strptime(f"{date_str} {hour}:{minute}:{second}", "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
        return None
    
    def classify_by_extension(self, extension: str) -> Tuple[Optional[str], float]:
        """Classify by file extension."""
        ext_lower = extension.lower()
        if ext_lower in self.ext_to_category:
            return self.ext_to_category[ext_lower], 0.9
        return None, 0.0
    
    def classify_by_mime(self, mime_type: Optional[str]) -> Tuple[Optional[str], float]:
        """Classify by MIME type."""
        if not mime_type:
            return None, 0.0
        
        if mime_type.startswith('image/'):
            return 'images', 0.8
        elif mime_type.startswith('video/'):
            return 'videos', 0.8
        elif mime_type.startswith('audio/'):
            return 'audio', 0.8
        elif mime_type == 'application/pdf':
            return 'documents', 0.9
        elif mime_type in ['application/zip', 'application/x-tar', 'application/gzip', 
                          'application/x-bzip2', 'application/x-7z-compressed']:
            return 'archives', 0.8
        elif mime_type in ['application/x-apple-diskimage', 'application/octet-stream']:
            # Could be installer
            return 'installers', 0.5
        return None, 0.0
    
    def classify_by_filename(self, filename: str) -> Tuple[Optional[str], float, str]:
        """Classify by filename patterns."""
        filename_lower = filename.lower()
        
        # Travel-related
        travel_keywords = ['travel', 'trip', 'vacation', 'holiday', 'flight', 'hotel', 
                          'boarding', 'ticket', 'itinerary', 'passport', 'visa']
        for kw in travel_keywords:
            if kw in filename_lower:
                return 'travel', 0.7, f"Filename contains '{kw}'"
        
        # Finance-related
        finance_keywords = ['invoice', 'receipt', 'bill', 'payment', 'bank', 'statement',
                           'tax', 'finance', 'budget', 'expense']
        for kw in finance_keywords:
            if kw in filename_lower:
                return 'finance', 0.7, f"Filename contains '{kw}'"
        
        # Certificate-related
        cert_keywords = ['certificate', 'cert', 'diploma', 'degree', 'license', 'permit']
        for kw in cert_keywords:
            if kw in filename_lower:
                return 'certificates', 0.7, f"Filename contains '{kw}'"
        
        # CV/Career
        cv_keywords = ['cv', 'resume', 'cover', 'letter', 'portfolio', 'linkedin']
        for kw in cv_keywords:
            if kw in filename_lower:
                return 'cv_career', 0.7, f"Filename contains '{kw}'"
        
        # Personal documents
        personal_keywords = ['personal', 'private', 'family', 'medical', 'health', 'insurance']
        for kw in personal_keywords:
            if kw in filename_lower:
                return 'personal', 0.6, f"Filename contains '{kw}'"
        
        # Code projects
        code_keywords = ['project', 'repo', 'source', 'code', 'app', 'script']
        for kw in code_keywords:
            if kw in filename_lower:
                return 'projects', 0.5, f"Filename contains '{kw}'"
        
        return None, 0.0, ""
    
    def detect_travel_destination(self, filename: str, path: pathlib.Path) -> Tuple[Optional[str], float]:
        """Detect travel destination from filename or path."""
        text = (filename + " " + str(path)).lower()
        
        for dest in self.known_destinations:
            if dest.lower() in text:
                return dest, self.travel_confidence
        
        # Try to detect from common patterns
        dest_patterns = [
            r'(croatia|norway|spain|iceland|new.?zealand|italy|france|germany|japan|thailand|vietnam|bali|iceland)',
        ]
        for pattern in dest_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).title(), 0.6
        
        return None, 0.0
    
    def classify(self, file_info: FileInfo) -> FileInfo:
        """Classify a file and update its category."""
        filename = file_info.filename
        extension = file_info.extension
        mime_type = file_info.mime_type
        
        # Check for screenshots first (highest priority for Pictures)
        if self.is_screenshot(filename):
            file_info.category = Category.SCREENSHOTS
            file_info.confidence = 0.95
            file_info.reason = "Matches screenshot filename pattern"
            return file_info
        
        # Classify by extension
        ext_cat, ext_conf = self.classify_by_extension(extension)
        
        # Classify by MIME type
        mime_cat, mime_conf = self.classify_by_mime(mime_type)
        
        # Classify by filename
        name_cat, name_conf, name_reason = self.classify_by_filename(filename)
        
        # Determine best classification
        candidates = []
        if ext_cat:
            candidates.append((ext_cat, ext_conf, "extension"))
        if mime_cat:
            candidates.append((mime_cat, mime_conf, "MIME type"))
        if name_cat:
            candidates.append((name_cat, name_conf, name_reason))
        
        if candidates:
            # Sort by confidence
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_cat, best_conf, best_reason = candidates[0]
            
            # Map string category to Category enum
            cat_map = {
                'documents': Category.DOCUMENTS,
                'images': Category.IMAGES,
                'videos': Category.VIDEOS,
                'audio': Category.AUDIO,
                'archives': Category.ARCHIVES,
                'installers': Category.INSTALLERS,
                'code': Category.CODE,
                'data': Category.DATA,
                'travel': Category.TRAVEL,
                'finance': Category.FINANCE,
                'certificates': Category.CERTIFICATES,
                'cv_career': Category.CV_CAREER,
                'projects': Category.PROJECTS,
                'personal': Category.PERSONAL,
            }
            
            if best_cat in cat_map:
                file_info.category = cat_map[best_cat]
                file_info.confidence = best_conf
                file_info.reason = f"Classified by {best_reason}"
            else:
                file_info.category = Category.NEEDS_REVIEW
                file_info.confidence = 0.0
                file_info.reason = "No matching category"
        else:
            file_info.category = Category.NEEDS_REVIEW
            file_info.confidence = 0.0
            file_info.reason = "Unable to classify"
        
        # Check for travel destination
        if file_info.category in [Category.IMAGES, Category.VIDEOS, Category.TRAVEL]:
            dest, dest_conf = self.detect_travel_destination(filename, file_info.path)
            if dest:
                file_info.category = Category.TRAVEL
                file_info.confidence = max(file_info.confidence, dest_conf)
                file_info.reason += f"; travel destination: {dest}"
        
        # Low confidence -> NeedsReview
        if file_info.confidence < self.confidence_threshold:
            file_info.category = Category.NEEDS_REVIEW
            file_info.needs_review = True
            file_info.reason += f" (confidence {file_info.confidence:.2f} < threshold {self.confidence_threshold})"
        
        return file_info
    
    def propose_destination(self, file_info: FileInfo, config: dict) -> Optional[pathlib.Path]:
        """Propose a centralized destination; protected categories get no proposal."""
        home = pathlib.Path.home()
        cat = file_info.category
        if file_info.work_review or cat in {
            Category.CODE, Category.PROJECTS, Category.NEEDS_REVIEW,
            Category.WORK_REVIEW_REQUIRED, Category.UNKNOWN
        }:
            return None

        configured = config.get('destinations', {})
        defaults = {
            Category.IMAGES: '~/Pictures/Organized',
            Category.VIDEOS: '~/Movies/Organized',
            Category.AUDIO: '~/Music/Organized',
            Category.ARCHIVES: '~/Downloads/Archives',
            Category.INSTALLERS: '~/Downloads/Installers',
            Category.DOCUMENTS: '~/Documents/Organized',
            Category.CV_CAREER: '~/Documents/CV-Career',
            Category.FINANCE: '~/Documents/Finance',
            Category.TRAVEL: '~/Documents/Travel',
            Category.CERTIFICATES: '~/Documents/Certificates',
            Category.PERSONAL: '~/Documents/Personal',
            Category.DATA: '~/Documents/Data',
            Category.REPOSITORY_ARCHIVE: '~/Downloads/Archives/Repositories/Unknown',
        }

        def expand_destination(value: str) -> pathlib.Path:
            if value == '~':
                return home
            if value.startswith('~/'):
                return home / value[2:]
            return pathlib.Path(value)

        def destination_root(category: Category) -> pathlib.Path:
            value = configured.get(category.value, defaults.get(category, '~/Downloads/Organized'))
            return expand_destination(value)
        
        if cat == Category.SCREENSHOTS:
            date = self.extract_screenshot_date(file_info.filename) or file_info.created or file_info.modified or datetime.now()
            year = date.strftime("%Y")
            month = date.strftime("%Y-%m")
            root = expand_destination(configured.get('Screenshots', '~/Pictures/Screenshots'))
            return root / year / month / file_info.filename
        
        elif cat == Category.TRAVEL:
            dest, _ = self.detect_travel_destination(file_info.filename, file_info.path)
            if dest:
                return destination_root(cat) / dest / file_info.filename
        elif cat == Category.ARCHIVES:
            return pathlib.Path(home / 'Downloads/Archives/General') / file_info.filename
        elif cat == Category.REPOSITORY_ARCHIVE:
            if file_info.archive_origin == 'personal':
                root = home / 'Downloads/Archives/Repositories/Personal' / (file_info.archive_owner or 'Unknown')
            elif file_info.archive_origin in {'company', 'company_internal'}:
                return None
            else:
                root = home / 'Downloads/Archives/Repositories/Unknown'
            return root / file_info.filename
        return destination_root(cat) / file_info.filename


def create_classifier(config: dict) -> Classifier:
    """Factory function to create a Classifier."""
    return Classifier(config)
