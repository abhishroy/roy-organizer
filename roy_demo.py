"""Synthetic fake-Mac generator and safe execute/undo demonstration."""
import pathlib
import tempfile
import zipfile

from roy_executor import SandboxExecutor
from roy_plan import PlanOperation


def create_demo_tree(root: pathlib.Path) -> dict:
    for name in ['Desktop','Downloads','Documents','Pictures','Movies','Projects']:
        (root/name).mkdir(parents=True, exist_ok=True)
    created = []
    for index in range(50):
        path = root/'Desktop'/f'Screenshot 2026-01-{index % 28 + 1:02d} at 10.00.{index:02d}.png'
        path.write_bytes(b'fake png'); created.append(path)
    for name in ['photo.jpg','document.pdf','video.mp4','installer.dmg','mystery.xyz']:
        path = root/'Downloads'/name; path.write_bytes(b'demo'); created.append(path)
    duplicate = root/'Downloads'/'duplicate.txt'; duplicate.write_text('same')
    (root/'Documents'/'duplicate.txt').write_text('same')
    project = root/'Projects'/'app'; project.mkdir(); (project/'.git').mkdir(); (project/'package.json').write_text('{}')
    (project/'main.js').write_text('demo')
    for hidden in [root/'.aws', root/'.kube', root/'.oh-my-zsh']:
        hidden.mkdir(); (hidden/'fake-config').write_text('synthetic')
    (root/'.zshrc').write_text('# synthetic')
    (root/'Desktop'/'workspace.code-workspace').write_text('{}')
    (root/'Desktop'/'green.yaml').write_text('apiVersion: v1\nkind: Config\nclusters:\ncontexts:\ncurrent-context: x\nusers:\n')
    (root/'Desktop'/'deployment.yaml').write_text('apiVersion: apps/v1\nkind: Deployment\n')
    (root/'Desktop'/'values.yaml').write_text('replicaCount: 2\n')
    for name, remote in [('personal.zip','github.com/abhishroy/demo'),
                         ('company.zip','github.com/example-company/demo'),
                         ('internal.zip','github.internal.invalid/demo'), ('unknown.zip','local')]:
        with zipfile.ZipFile(root/'Downloads'/name, 'w') as archive:
            archive.writestr('demo-main/README.md', remote)
            archive.writestr('demo-main/.gitignore', '*.pyc')
            archive.writestr('demo-main/pyproject.toml', '[project]')
            archive.writestr('demo-main/src/main.py', 'print("demo")')
    with zipfile.ZipFile(root/'Downloads'/'holiday.zip', 'w') as archive:
        archive.writestr('photos/a.jpg', b'demo')
    return {'root': root, 'created': created}


def run_demo() -> dict:
    with tempfile.TemporaryDirectory(prefix='roy-organizer-sandbox-', dir='/tmp') as value:
        root = pathlib.Path(value); create_demo_tree(root)
        source = next((root/'Desktop').glob('Screenshot*.png'))
        stat = source.stat(); destination = root/'Pictures'/'Screenshots'/source.name
        operation = PlanOperation(str(source), str(destination), 'Screenshots', 1.0,
                                  'Synthetic demo screenshot', 'approved', stat.st_size,
                                  'Desktop', stat.st_mtime)
        executor = SandboxExecutor(root, root/'logs/transactions.jsonl')
        before = source.read_bytes(); result = executor.execute(operation, 'demo')
        moved = destination.exists() and not source.exists()
        undone = executor.undo('demo')
        intact = source.exists() and source.read_bytes() == before and not destination.exists()
        return {'generated': 50 + 5 + 2 + 4 + 8, 'moves': int(moved),
                'blocked': 0, 'undo': undone, 'integrity': intact, 'result': result}
