"""Optional local-only Ollama suggestions. Disabled by default."""
import pathlib
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class AISuggestion:
    category: str
    confidence: str = 'AI suggestion'
    source: str = 'local Ollama'


class LocalAI:
    def __init__(self, config: dict):
        self.config = config.get('ai_classification', {})

    @property
    def enabled(self) -> bool:
        return self.config.get('enabled', False) is True

    def available_models(self) -> list[str]:
        if not shutil.which('ollama'):
            return []
        try:
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return []
            return [line.split()[0] for line in result.stdout.splitlines()[1:] if line.split()]
        except (OSError, subprocess.TimeoutExpired):
            return []

    def suggest_filename(self, path: pathlib.Path) -> AISuggestion | None:
        """Ask an installed local model about a filename only; never file contents."""
        if not self.enabled:
            return None
        model = self.config.get('model')
        if not model or model not in self.available_models():
            return None
        prompt = ('Classify this filename into one short category. Do not propose actions: '
                  + path.name)
        try:
            result = subprocess.run(['ollama', 'run', model, prompt], capture_output=True,
                                    text=True, timeout=self.config.get('timeout', 30))
            if result.returncode == 0 and result.stdout.strip():
                return AISuggestion(result.stdout.strip().splitlines()[0][:100])
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None
