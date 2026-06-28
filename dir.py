from pathlib import Path

def startup():

    if not detect_dir():
        create_dir()

    # assign documents/instance1 to dir
    directory_path = str(get_target_path())
    return directory_path


def get_target_path():
    return Path.home() / "Documents" / "instance1"


def detect_dir():
    target = get_target_path()
    return target.is_dir()


def create_dir():
    target = get_target_path()

    target.mkdir(parents=True, exist_ok=True)
    print(f"Created directory at: {target}")