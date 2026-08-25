import os
import glob
import shutil
from datetime import datetime


def latest_file(folder, patterns=("*.pdf",)):
    files = []

    for pattern in patterns:
        files.extend(
            glob.glob(os.path.join(folder, pattern))
        )

    if not files:
        return None

    return max(files, key=os.path.getmtime)


def latest_files(folder, patterns=("*.pdf",)):
    files = []

    for pattern in patterns:
        files.extend(
            glob.glob(os.path.join(folder, pattern))
        )

    files.sort(key=os.path.getmtime)

    return files


def archive_file(file_path, archive_folder):

    if not file_path:
        return

    os.makedirs(archive_folder, exist_ok=True)

    filename = os.path.basename(file_path)

    name, ext = os.path.splitext(filename)

    new_name = (
        f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    )

    shutil.move(
        file_path,
        os.path.join(archive_folder, new_name)
    )