"""Build clean production zip — only files needed to run the dashboard."""
import os, zipfile

SRC = r"C:\Users\1039081\Downloads\cluade\awr-dashboard"
ZIP_OUT = r"C:\Users\1039081\Downloads\cluade\oravision-awr-dashboard.zip"

# Exactly the dirs/files that run the dashboard — nothing else
INCLUDE_DIRS = {
    'backend/models',
    'backend/routers',
    'backend/services',
    'backend/templates',
    'backend/static',
    'backend/data',
}

INCLUDE_ROOT_FILES = {
    'start.bat',
    'requirements.txt',
    '.gitignore',
    '.oravision_port',
}

INCLUDE_BACKEND_FILES = {
    'main.py',
    'requirements.txt',
    '.env',
}

# Docs (optional but useful for deployment)
INCLUDE_DOCS = True

SKIP_NAMES = {'__pycache__', '.git', 'node_modules', '.gitkeep'}


def should_include_file(rel_path):
    """Decide if a file belongs in the production zip."""
    parts = rel_path.replace('\\', '/').split('/')
    fname = parts[-1]

    # Skip __pycache__ anywhere
    if '__pycache__' in parts:
        return False

    # Root-level files
    if len(parts) == 1:
        return fname in INCLUDE_ROOT_FILES

    # Backend root files
    if len(parts) == 2 and parts[0] == 'backend':
        return fname in INCLUDE_BACKEND_FILES

    # Backend subdirectories
    if parts[0] == 'backend':
        subdir = '/'.join(parts[:2])
        if subdir in INCLUDE_DIRS:
            # Skip _ prefixed files EXCEPT __init__.py and _pe_bootstrap.js
            if fname.startswith('_') and fname not in ('__init__.py', '_pe_bootstrap.js'):
                return False
            if fname in SKIP_NAMES:
                return False
            return True

    # Docs
    if parts[0] == 'docs' and INCLUDE_DOCS:
        return True

    return False


def build_zip():
    if os.path.exists(ZIP_OUT):
        os.remove(ZIP_OUT)

    root_prefix = 'oravision-awr-dashboard'
    count = 0
    total_size = 0

    with zipfile.ZipFile(ZIP_OUT, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(SRC):
            # Prune skipped dirs
            dirnames[:] = [d for d in dirnames if d not in SKIP_NAMES]

            for fname in sorted(filenames):
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, SRC)

                if should_include_file(rel_path):
                    arc_name = f"{root_prefix}/{rel_path.replace(os.sep, '/')}"
                    zf.write(full_path, arc_name)
                    fsize = os.path.getsize(full_path)
                    total_size += fsize
                    count += 1

    zip_size = os.path.getsize(ZIP_OUT) / (1024 * 1024)
    print(f"Created: {ZIP_OUT}")
    print(f"  Production files: {count}")
    print(f"  Zip size: {zip_size:.1f} MB")
    print(f"  Uncompressed: {total_size / (1024*1024):.1f} MB")
    print()

    # Show contents
    with zipfile.ZipFile(ZIP_OUT, 'r') as zf:
        names = sorted(zf.namelist())
        print("Contents:")
        for n in names:
            size = zf.getinfo(n).file_size
            label = f"  {n}"
            if size > 1024*1024:
                label += f"  ({size/1024/1024:.1f} MB)"
            elif size > 1024:
                label += f"  ({size/1024:.0f} KB)"
            print(label)


if __name__ == '__main__':
    build_zip()
