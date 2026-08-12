"""Lightweight Tkinter planning preview; no execution controls."""
import pathlib
import pickle

from roy_classify import Category, create_classifier
from roy_plan import ReviewPlan


class GUIController:
    def __init__(self, config: dict, scan_path=pathlib.Path('data/last_scan.pkl')):
        self.config = config
        self.scan_path = pathlib.Path(scan_path)

    def load(self):
        with self.scan_path.open('rb') as handle:
            return pickle.load(handle)

    def counts(self) -> dict:
        _, stats = self.load()
        return dict(stats.by_category)

    def create_plan(self, categories) -> ReviewPlan:
        files, stats = self.load()
        classifier = create_classifier(self.config)
        for item in files:
            item.proposed_destination = classifier.propose_destination(item, self.config)
        return ReviewPlan.from_inventory(files, stats, categories)


def launch(config: dict) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print('GUI unavailable: Tkinter is not installed.')
        return
    controller = GUIController(config)
    if not controller.scan_path.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    root = tk.Tk(); root.title('ROY Organizer — Early Preview'); root.geometry('520x560')
    tk.Label(root, text='ROY Organizer', font=('Helvetica', 24, 'bold')).pack(pady=16)
    tk.Label(root, text='Planning preview — real execution is disabled').pack()
    variables = {}
    choices = [Category.SCREENSHOTS, Category.IMAGES, Category.DOCUMENTS,
               Category.VIDEOS, Category.ARCHIVES, Category.REPOSITORY_ARCHIVE]
    counts = controller.counts()
    for category in choices:
        variable = tk.BooleanVar(); variables[category] = variable
        tk.Checkbutton(root, text=f'{category.value} ({counts.get(category.value, 0):,})',
                       variable=variable, anchor='w').pack(fill='x', padx=60, pady=4)
    def save_plan():
        selected = [category for category, variable in variables.items() if variable.get()]
        plan = controller.create_plan(selected)
        plan.save(pathlib.Path(config.get('review', {}).get('plan_file', 'data/current_plan.json')))
        summary = plan.summary()
        messagebox.showinfo('Plan saved', f"{summary['pending']:,} suggestions saved.\n0 files deleted.\n0 files executed.")
    tk.Button(root, text='Review Suggestions / Save Plan', command=save_plan).pack(pady=24)
    tk.Button(root, text='Quit Safely', command=root.destroy).pack()
    root.mainloop()
