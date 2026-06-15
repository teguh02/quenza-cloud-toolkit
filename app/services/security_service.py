"""Security Module Services: System Info, Task Manager, Firewall."""

import platform
import subprocess
from typing import Any, Dict, List

import psutil


def get_system_info() -> Dict[str, Any]:
    """Retrieve basic system metrics."""
    # RAM
    mem = psutil.virtual_memory()
    
    # Disk (root)
    disk_path = "C:\\" if platform.system() == "Windows" else "/"
    try:
        disk = psutil.disk_usage(disk_path)
    except Exception:
        disk = None
        
    # Network IPs
    ips = []
    try:
        for interface, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family.name in ('AF_INET', 'AF_INET6'):
                    ips.append({"interface": interface, "ip": snic.address})
    except Exception:
        pass
                
    # Basic Python Packages (since package managers are varied)
    # We'll just run pip freeze for a quick list
    try:
        pip_out = subprocess.check_output(["pip", "freeze"], text=True)
        packages = pip_out.splitlines()
    except Exception:
        packages = ["Gagal membaca daftar paket pip."]

    return {
        "os": platform.system(),
        "release": platform.release(),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram": {
            "total": mem.total,
            "used": mem.used,
            "percent": mem.percent
        },
        "disk": {
            "total": disk.total if disk else 0,
            "used": disk.used if disk else 0,
            "percent": disk.percent if disk else 0,
            "path": disk_path
        },
        "ips": ips,
        "packages": packages
    }


def get_processes() -> List[Dict[str, Any]]:
    """List running processes."""
    processes = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'status']):
        try:
            info = p.info
            processes.append({
                "pid": info["pid"],
                "name": info["name"] or "Unknown",
                "user": info["username"] or "Unknown",
                "cpu": round(info["cpu_percent"] or 0.0, 1),
                "ram": round(info["memory_percent"] or 0.0, 1),
                "status": info["status"]
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    # sort by cpu desc
    processes.sort(key=lambda x: x["cpu"], reverse=True)
    # limit to top 100 to avoid huge payload
    return processes[:100]


def kill_process(pid: int) -> bool:
    """Kill a process by PID."""
    try:
        p = psutil.Process(pid)
        p.kill()
        return True
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        raise PermissionError(f"Akses ditolak untuk membunuh PID {pid}.")


class FirewallAdapter:
    def get_rules(self) -> List[Dict[str, Any]]:
        raise NotImplementedError
        
    def add_rule(self, port: int, protocol: str, action: str) -> bool:
        raise NotImplementedError
        
    def delete_rule(self, port: int, protocol: str) -> bool:
        raise NotImplementedError


class LinuxUFWAdapter(FirewallAdapter):
    def get_rules(self) -> List[Dict[str, Any]]:
        try:
            out = subprocess.check_output(["sudo", "ufw", "status", "numbered"], text=True)
            lines = out.splitlines()
            rules = []
            for line in lines:
                if line.strip():
                    rules.append({"raw": line.strip()})
            return rules
        except Exception as e:
            return [{"raw": f"Gagal membaca UFW (pastikan sudo aktif tanpa password): {e}"}]

    def add_rule(self, port: int, protocol: str, action: str) -> bool:
        # action = "allow" or "deny"
        try:
            cmd = ["sudo", "ufw", action, f"{port}/{protocol}"]
            subprocess.check_call(cmd)
            return True
        except Exception:
            return False
            
    def delete_rule(self, port: int, protocol: str) -> bool:
        try:
            # Sederhananya coba hapus allow dan deny
            cmd1 = ["sudo", "ufw", "delete", "allow", f"{port}/{protocol}"]
            cmd2 = ["sudo", "ufw", "delete", "deny", f"{port}/{protocol}"]
            success = False
            try:
                subprocess.check_call(cmd1)
                success = True
            except Exception:
                pass
            try:
                subprocess.check_call(cmd2)
                success = True
            except Exception:
                pass
            return success
        except Exception:
            return False


class WindowsNetshAdapter(FirewallAdapter):
    def get_rules(self) -> List[Dict[str, Any]]:
        try:
            out = subprocess.check_output(["netsh", "advfirewall", "show", "currentprofile"], text=True, errors="replace")
            lines = out.splitlines()
            rules = []
            for line in lines:
                if line.strip():
                    rules.append({"raw": line.strip()})
            return rules
        except Exception as e:
            return [{"raw": f"Gagal membaca netsh: {e}"}]

    def add_rule(self, port: int, protocol: str, action: str) -> bool:
        act = "allow" if action.lower() == "allow" else "block"
        name = f"Quenza_{act}_{port}_{protocol}"
        try:
            cmd = [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={name}", f"dir=in", f"action={act}", f"protocol={protocol}", f"localport={str(port)}"
            ]
            subprocess.check_call(cmd)
            return True
        except Exception:
            return False

    def delete_rule(self, port: int, protocol: str) -> bool:
        name_allow = f"Quenza_allow_{port}_{protocol}"
        name_block = f"Quenza_block_{port}_{protocol}"
        success = False
        try:
            subprocess.check_call(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name_allow}"])
            success = True
        except Exception:
            pass
        try:
            subprocess.check_call(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={name_block}"])
            success = True
        except Exception:
            pass
        return success


def get_firewall_adapter() -> FirewallAdapter:
    """Return platform specific firewall adapter."""
    if platform.system() == "Windows":
        return WindowsNetshAdapter()
    return LinuxUFWAdapter()


class OsSchedulerAdapter:
    def get_tasks(self) -> List[Dict[str, Any]]:
        raise NotImplementedError
        
    def add_task(self, name: str, schedule: str, command: str) -> bool:
        raise NotImplementedError
        
    def delete_task(self, name: str) -> bool:
        raise NotImplementedError


class LinuxCronAdapter(OsSchedulerAdapter):
    def get_tasks(self) -> List[Dict[str, Any]]:
        try:
            out = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.STDOUT)
            lines = out.splitlines()
            tasks = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Parse schedule (first 5 fields) and command
                parts = line.split(maxsplit=5)
                if len(parts) >= 6:
                    schedule = " ".join(parts[:5])
                    command = parts[5]
                    tasks.append({
                        "name": f"Cron: {command[:20]}...",
                        "schedule": schedule,
                        "command": command,
                        "next_run": "-",
                        "raw": line
                    })
                else:
                    tasks.append({"name": "Unknown", "schedule": "-", "command": line, "next_run": "-", "raw": line})
            return tasks
        except subprocess.CalledProcessError:
            # crontab -l exits with 1 if no crontab for user
            return []
        except Exception as e:
            return [{"name": "Error", "schedule": "-", "command": f"Failed to read crontab: {e}", "next_run": "-", "raw": str(e)}]

    def add_task(self, name: str, schedule: str, command: str) -> bool:
        try:
            new_job = f"# {name}\n{schedule} {command}\n"
            try:
                current = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                current = ""
            
            new_crontab = current + "\n" + new_job
            
            proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
            proc.communicate(input=new_crontab)
            return proc.returncode == 0
        except Exception:
            return False

    def delete_task(self, name: str) -> bool:
        # In Linux context, the frontend passes `raw` as the name identifier.
        try:
            current = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.STDOUT)
            lines = current.splitlines()
            new_lines = []
            deleted = False
            for line in lines:
                if line.strip() == name.strip():
                    deleted = True
                    continue
                new_lines.append(line)
            
            if not deleted:
                return False
                
            new_crontab = "\n".join(new_lines) + "\n"
            proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
            proc.communicate(input=new_crontab)
            return proc.returncode == 0
        except Exception:
            return False


class WindowsTaskAdapter(OsSchedulerAdapter):
    def get_tasks(self) -> List[Dict[str, Any]]:
        import csv
        import io
        try:
            out = subprocess.check_output(["schtasks", "/query", "/fo", "CSV", "/v"], text=True, errors="replace")
            reader = csv.DictReader(io.StringIO(out))
            tasks = []
            for row in reader:
                if not row or "TaskName" not in row or not row["TaskName"]:
                    continue
                task_name = row.get("TaskName", "")
                if task_name == "TaskName":
                    continue
                # Sembunyikan tugas internal Microsoft untuk mengurangi kebisingan UI
                if task_name.startswith("\\Microsoft\\"):
                    continue
                
                tasks.append({
                    "name": task_name.strip('\\'),
                    "schedule": row.get("Schedule Type", "-") + " " + row.get("Start Time", ""),
                    "command": row.get("Task To Run", ""),
                    "next_run": row.get("Next Run Time", "-"),
                    "raw": task_name
                })
            return tasks
        except Exception as e:
            return [{"name": "Error", "schedule": "-", "command": f"Failed to read schtasks: {e}", "next_run": "-", "raw": str(e)}]

    def add_task(self, name: str, schedule: str, command: str) -> bool:
        # Format schedule dari FE: "DAILY 10:00" atau "MINUTE 15"
        try:
            parts = schedule.strip().split(maxsplit=1)
            sc = parts[0].upper()
            
            cmd = ["schtasks", "/create", "/tn", f"Quenza_{name}", "/tr", command, "/sc", sc]
            if len(parts) > 1 and sc not in ("ONSTART", "ONLOGON", "ONIDLE"):
                # Windows schtasks time format: HH:mm
                cmd.extend(["/st", parts[1]])
                
            subprocess.check_call(cmd)
            return True
        except Exception:
            return False

    def delete_task(self, name: str) -> bool:
        try:
            # name adalah raw task_name dari Windows
            subprocess.check_call(["schtasks", "/delete", "/tn", name, "/f"])
            return True
        except Exception:
            return False


def get_os_scheduler_adapter() -> OsSchedulerAdapter:
    """Return platform specific OS scheduler adapter."""
    if platform.system() == "Windows":
        return WindowsTaskAdapter()
    return LinuxCronAdapter()
