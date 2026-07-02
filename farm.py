import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).parent


@dataclass
class Instance:
    id: int
    name: str
    label: str
    serial: str
    template: str
    created: str


class Farm:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "farm.json"
        self.instances: list[Instance] = []
        self.next_id = 1
        self._load()

    def _load(self):
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            self.instances = [Instance(**i) for i in raw.get("instances", [])]
            self.next_id = raw.get("next_id", max((i.id for i in self.instances), default=0) + 1)

    def _save(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "next_id": self.next_id,
            "instances": [asdict(i) for i in self.instances],
        }, indent=2))

    @staticmethod
    def default_label(instance_id):
        row = (instance_id - 1) // 26
        col = (instance_id - 1) % 26 + 1
        return f"{chr(ord('a') + row)}{col}"

    def ports(self, instance_id):
        return {
            "moonraker": 37124 + instance_id,
            "mainsail": 8080 + instance_id,
            "uds": f"/tmp/instances/instance_{instance_id}.sock",
        }

    def instance_dir(self, instance_id):
        return self.data_dir / f"instance{instance_id}"

    def printer_cfg(self, instance_id):
        return self.instance_dir(instance_id) / "printer.cfg"

    def moonraker_conf(self, instance_id):
        return self.instance_dir(instance_id) / "moonraker.conf"

    def moonraker_data(self, instance_id):
        return self.instance_dir(instance_id) / "moonraker_data"

    def mainsail_dir(self, instance_id):
        return self.instance_dir(instance_id) / "mainsail"

    def create(self, name="", label=None, serial="", template_path=""):
        inst = Instance(
            id=self.next_id,
            name=name or f"Instance {self.next_id}",
            label=label or self.default_label(self.next_id),
            serial=serial,
            template=template_path or "",
            created=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        self.instances.append(inst)
        self.next_id += 1
        self._bootstrap(inst, serial, template_path)
        self._save()
        return inst

    def _bootstrap(self, inst, serial, template_path):
        d = self.instance_dir(inst.id)
        d.mkdir(parents=True, exist_ok=True)

        if template_path:
            shutil.copy(template_path, d / "printer.cfg")
            if serial:
                self._update_serial(inst, serial)
        else:
            (d / "printer.cfg").write_text(f"# Instance {inst.id}\n[stepper_x]\n")

        self._write_moonraker_conf(inst)
        self._setup_mainsail(inst)

    def remove(self, instance_id):
        inst = self._get(instance_id)
        d = self.instance_dir(instance_id)
        if d.exists():
            shutil.rmtree(d)
        self.instances.remove(inst)
        self._save()

    def _get(self, instance_id):
        for i in self.instances:
            if i.id == instance_id:
                return i
        raise KeyError(f"Instance {instance_id} not found")

    def assign_serial(self, instance_id, device_path):
        inst = self._get(instance_id)
        inst.serial = device_path
        self._update_serial(inst, device_path)
        self._save()

    def rename(self, instance_id, name):
        self._get(instance_id).name = name
        self._save()

    def relabel(self, instance_id, label):
        self._get(instance_id).label = label
        self._save()

    def find_by_name(self, name):
        for i in self.instances:
            if i.name.lower() == name.lower():
                return i
        return None

    def find_by_label(self, label):
        for i in self.instances:
            if i.label.lower() == label.lower():
                return i
        return None

    def label_exists(self, label):
        return self.find_by_label(label) is not None

    def name_exists(self, name):
        return self.find_by_name(name) is not None

    def _update_serial(self, inst, device_path):
        cfg = self.printer_cfg(inst.id)
        lines = cfg.read_text().splitlines()
        in_mcu = False
        found_serial = False
        for i, line in enumerate(lines):
            s = line.strip()
            if s == "[mcu]":
                in_mcu = True
            elif in_mcu and s.startswith("serial:"):
                lines[i] = f"serial: {device_path}"
                found_serial = True
                break
            elif in_mcu and s.startswith("["):
                break
        if not found_serial:
            lines.append("[mcu]")
            lines.append(f"serial: {device_path}")
        cfg.write_text("\n".join(lines) + "\n")

    def _write_moonraker_conf(self, inst):
        p = self.ports(inst.id)
        self.moonraker_conf(inst.id).write_text(
            f"[server]\nhost: 0.0.0.0\nport: {p['moonraker']}\n"
            f"klippy_uds_address: {p['uds']}\n\n"
            f"[authorization]\ncors_domains:\n"
            f"    http://localhost:{p['mainsail']}\n"
            f"trusted_clients:\n    127.0.0.1\n    192.168.0.0/16\n"
        )

    def _setup_mainsail(self, inst):
        src = APP_DIR / "mainsail_web"
        dst = self.mainsail_dir(inst.id)
        dst.mkdir(parents=True, exist_ok=True)

        for item in src.iterdir():
            if item.name == "config.json":
                continue
            link = dst / item.name
            if not link.exists():
                rel = os.path.relpath(item, dst)
                link.symlink_to(rel)

        p = self.ports(inst.id)
        (dst / "config.json").write_text(json.dumps({
            "hostname": "localhost",
            "port": p["moonraker"],
            "instancesDB": "moonraker",
        }, indent=2))

    def assigned_serials(self):
        return {i.serial for i in self.instances if i.serial}

    def unassigned_usb_devices(self, all_devices):
        assigned = self.assigned_serials()
        return [d for d in all_devices if d not in assigned]
