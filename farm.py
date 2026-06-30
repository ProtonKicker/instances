import json
import shutil
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


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

    def _get(self, instance_id):
        for inst in self.instances:
            if inst.id == instance_id:
                return inst
        raise KeyError(instance_id)

    def _instance_dir(self, instance_id):
        return self.data_dir / f"instance{instance_id}"

    def create(self, label, serial="", template_path=""):
        inst = Instance(
            id=self.next_id,
            name=f"Instance {self.next_id}",
            label=label,
            serial=serial,
            template=template_path,
            created=datetime.now().isoformat(),
        )
        self.instances.append(inst)
        self.next_id += 1

        inst_dir = self._instance_dir(inst.id)
        inst_dir.mkdir(parents=True, exist_ok=True)

        if template_path:
            cfg_src = Path(template_path)
            cfg_dst = inst_dir / "printer.cfg"
            shutil.copy2(str(cfg_src), str(cfg_dst))
            if serial:
                self._update_serial_in_file(str(cfg_dst), serial)

        self._setup_instance_dirs(inst)
        self._save()
        return inst

    def remove(self, instance_id):
        inst = self._get(instance_id)
        self.instances.remove(inst)
        inst_dir = self._instance_dir(instance_id)
        if inst_dir.exists():
            shutil.rmtree(str(inst_dir))
        self._save()

    def rename(self, instance_id, name):
        self._get(instance_id).name = name
        self._save()

    def relabel(self, instance_id, label):
        self._get(instance_id).label = label
        self._save()

    def assign_serial(self, instance_id, device):
        inst = self._get(instance_id)
        inst.serial = device
        self._save()
        cfg_path = self._instance_dir(instance_id) / "printer.cfg"
        if cfg_path.exists():
            self._update_serial_in_file(str(cfg_path), device)

    def ports(self, instance_id):
        return {
            "moonraker": 37124 + instance_id,
            "mainsail": 8080 + instance_id,
        }

    def unassigned_usb_devices(self, all_devices):
        assigned = {inst.serial for inst in self.instances if inst.serial}
        return [d for d in all_devices if d not in assigned]

    @staticmethod
    def default_label(n):
        n -= 1
        letter = chr(ord('a') + (n % 26))
        number = n // 26 + 1
        return f"{letter}{number}"

    def _setup_instance_dirs(self, inst):
        inst_dir = self._instance_dir(inst.id)
        mr_data = inst_dir / "moonraker_data"
        mr_config = mr_data / "config"
        mr_data.mkdir(parents=True, exist_ok=True)
        mr_config.mkdir(parents=True, exist_ok=True)

        cfg_src = inst_dir / "printer.cfg"
        cfg_link = mr_config / "printer.cfg"
        if cfg_src.exists():
            if cfg_link.exists() or cfg_link.is_symlink():
                cfg_link.unlink()
            cfg_link.symlink_to(cfg_src)

        self._ensure_moonraker_conf(inst)

        mainsail_link = inst_dir / "mainsail"
        if not mainsail_link.exists():
            app_dir = Path(__file__).parent
            mainsail_src = app_dir / "mainsail_web"
            if mainsail_src.exists():
                mainsail_link.symlink_to(mainsail_src, target_is_directory=True)

    def _ensure_moonraker_conf(self, inst):
        p = self.ports(inst.id)
        inst_dir = self._instance_dir(inst.id)
        conf_path = inst_dir / "moonraker.conf"
        if conf_path.exists():
            return
        conf_path.write_text(
            f"[server]\n"
            f"host: 0.0.0.0\n"
            f"port: {p['moonraker']}\n"
            f"klippy_uds_address: /tmp/instances/instance_{inst.id}.sock\n\n"
            f"[authorization]\n"
            f"cors_domains:\n"
            f"    http://localhost:{p['mainsail']}\n"
            f"trusted_clients:\n"
            f"    127.0.0.1\n"
            f"    192.168.0.0/16\n\n"
        )

    @staticmethod
    def _update_serial_in_file(cfg_path, device_path):
        if not os.path.isfile(cfg_path):
            return False
        with open(cfg_path, "r") as f:
            lines = f.readlines()
        found_mcu = False
        serial_replaced = False
        with open(cfg_path, "w") as f:
            for line in lines:
                if line.strip().startswith("[mcu]"):
                    found_mcu = True
                elif found_mcu and line.strip().startswith("serial:"):
                    line = f"serial: {device_path}\n"
                    found_mcu = False
                    serial_replaced = True
                f.write(line)
        return serial_replaced
