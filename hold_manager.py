import queue
import shutil
import stat
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

REPO = "https://github.com/Zyvelia/Hold.git"
BRANCH = "main"
MAX_FILE = 100 * 1024 * 1024


def git(*args, cwd=None, paths=None):
    result = subprocess.run(
        ["git", *args], cwd=cwd, input=paths,
        stdin=subprocess.DEVNULL if paths is None else None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip()
            or f"git {args[0]} failed."
        )
    return result.stdout.strip()


def is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def collect(source, relative, files):
    if source.name.casefold() == ".git":
        return
    info = source.lstat()
    if is_link(info):
        raise ValueError(f"Select the actual file or folder instead of the link:\n{source}")
    if stat.S_ISDIR(info.st_mode):
        for item in source.iterdir():
            collect(item, relative / item.name, files)
        return
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Unsupported file type:\n{source}")
    if info.st_size > MAX_FILE:
        raise ValueError(f"GitHub's file limit is 100 MiB.\n{source}")
    key = relative.as_posix().casefold()
    if key in files and files[key][0] != source:
        raise ValueError(f"Two selections would write to the same repo path:\n{relative}")
    files[key] = (source, relative)


def upload(selection, status, base_dir=None):
    if shutil.which("git") is None:
        raise RuntimeError("Install Git for Windows, then reopen this manager.")

    status("Checking selected files…")
    files = {}
    for source in selection:
        if not source.name:
            raise ValueError("Choose individual files or folders inside the drive.")
        relative = source.relative_to(base_dir) if base_dir is not None else Path(source.name)
        if not relative.parts or ".." in relative.parts:
            raise ValueError("Select an item inside the scanned folder.")
        collect(source, relative, files)
    if not files:
        return "There were no files to upload."

    with tempfile.TemporaryDirectory(prefix="hold-manager-") as temp:
        checkout = Path(temp) / "repo"
        status("Cloning Zyvelia/Hold…")
        git("-c", f"init.defaultBranch={BRANCH}", "clone", "--", REPO, str(checkout))
        if git("symbolic-ref", "--short", "HEAD", cwd=checkout) != BRANCH:
            git("switch", BRANCH, cwd=checkout)

        status("Copying selected files…")
        for source, relative in files.values():
            destination = checkout / relative
            for entry in (relative, *relative.parents):
                path = checkout / entry
                if path.is_symlink() or (path.exists() and is_link(path.lstat())):
                    raise ValueError(f"The repo path is a link:\n{entry}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_dir():
                raise ValueError(f"A folder already occupies this repo path:\n{relative}")
            shutil.copyfile(source, destination)

        paths = "".join(f"{relative.as_posix()}\0" for _, relative in files.values())
        git("--literal-pathspecs", "add", "--force", "--pathspec-from-file=-",
            "--pathspec-file-nul", cwd=checkout, paths=paths)
        if not git("diff", "--cached", "--name-only", cwd=checkout):
            return "Nothing to upload. The selected files already match the repo."

        git("commit", "-m", "Upload selected files", cwd=checkout)
        status("Pushing to GitHub…")
        git("push", "origin", f"HEAD:refs/heads/{BRANCH}", cwd=checkout)
        return "Upload complete. Your files are on Zyvelia/Hold → main."


def main():
    base_dir = Path(__file__).resolve().parent
    root = tk.Tk()
    root.title("Hold Upload Manager")
    root.geometry("740x400")
    root.minsize(500, 300)

    panel = ttk.Frame(root, padding=16)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="Zyvelia/Hold  ·  main  ·  Public repository").pack(anchor="w")

    ttk.Label(panel, text=str(base_dir)).pack(anchor="w", pady=(4, 0))
    listing = ttk.Frame(panel)
    listing.pack(fill="both", expand=True, pady=12)
    tree = ttk.Treeview(listing, selectmode="extended", columns=("type",))
    tree.heading("#0", text="Name")
    tree.heading("type", text="Type")
    tree.column("type", width=75, stretch=False)
    scrollbar = ttk.Scrollbar(listing, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)

    buttons = ttk.Frame(panel)
    buttons.pack(fill="x")
    help_text = "Ctrl-click to select multiple items. Selecting a folder includes its contents."
    status = tk.StringVar(value=help_text)
    ttk.Label(panel, textvariable=status, wraplength=460).pack(anchor="w", pady=(12, 0))
    messages = queue.Queue()
    busy = False

    def populate(parent, folder):
        entries = []
        try:
            for item in folder.iterdir():
                if item.name.casefold() == ".git":
                    continue
                try:
                    info = item.lstat()
                except FileNotFoundError:
                    continue
                if not is_link(info):
                    entries.append((not stat.S_ISDIR(info.st_mode), item))
        except OSError as exc:
            status.set(f"Could not scan {folder}: {exc}")
            return

        tree.delete(*tree.get_children(parent))
        for is_file, item in sorted(entries, key=lambda entry: (entry[0], entry[1].name.casefold())):
            key = item.relative_to(base_dir).as_posix()
            tree.insert(parent, "end", iid=key, text=item.name,
                        values=("File" if is_file else "Folder",))
            if not is_file:
                tree.insert(key, "end", iid=key + "/", text="Expand to scan")

    def refresh():
        status.set(help_text)
        populate("", base_dir)

    def expand(event):
        key = tree.focus()
        if key and tree.exists(key + "/"):
            populate(key, base_dir / key)

    tree.bind("<<TreeviewOpen>>", expand)
    refresh()

    def worker(selection):
        try:
            result = upload(selection, lambda text: messages.put(("progress", text)), base_dir)
            messages.put(("done", result))
        except Exception as exc:
            messages.put(("error", str(exc)))

    def start():
        nonlocal busy
        selection = tuple(base_dir / key for key in tree.selection()
                          if not key.endswith("/"))
        if not selection:
            status.set("Select at least one file or folder.")
            return
        busy = True
        for button in controls:
            button.state(["disabled"])
        threading.Thread(target=worker, args=(selection,), daemon=True).start()

    def poll():
        nonlocal busy
        while not messages.empty():
            kind, text = messages.get_nowait()
            status.set(text if kind != "error" else "Upload failed.")
            if kind != "progress":
                busy = False
                for button in controls:
                    button.state(["!disabled"])
                if kind == "error":
                    messagebox.showerror("Upload failed", text, parent=root)
        root.after(100, poll)

    def close():
        if not busy:
            root.destroy()

    controls = [
        ttk.Button(buttons, text="Refresh", command=refresh),
        ttk.Button(buttons, text="Push to main", command=start),
    ]
    controls[0].pack(side="left")
    controls[1].pack(side="right")
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    root.mainloop()


if __name__ == "__main__":
    main()