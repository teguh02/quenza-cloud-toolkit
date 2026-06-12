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
