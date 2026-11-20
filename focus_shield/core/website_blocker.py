"""System-wide, temporary website blocks in the Windows hosts file."""
import ctypes
import os
import re
import subprocess
import threading
import time
import tempfile
from urllib.parse import urlsplit

BEGIN = b"# BEGIN PIANISSIMO MANAGED BLOCKS"
END = b"# END PIANISSIMO MANAGED BLOCKS"
HOSTS_PATH = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts")


def normalize_domain(value):
    value = value.strip().lower()
    if "://" in value:
        value = urlsplit(value).hostname or ""
    else:
        value = value.split("/", 1)[0].rstrip(".")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    labels = value.split(".")
    if len(labels) < 2 or len(value) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
        return None
    if labels[-1].isdigit() or value in ("localhost", "localdomain"):
        return None
    return value


def replace_managed_block(data, domains, expected_owner=None):
    """Replace only our marked lines, retaining all unrelated bytes."""
    lines = data.splitlines(keepends=True)
    clean = []
    inside = False
    owner = None
    for line in lines:
        marker = line.strip()
        if marker == BEGIN or marker.startswith(BEGIN + b" "):
            if inside:
                raise ValueError("Nested Pianissimo hosts markers")
            owner = marker[len(BEGIN):].strip().decode("ascii", errors="replace")
            inside = True
        elif marker == END:
            if not inside:
                raise ValueError("Unmatched Pianissimo hosts marker")
            inside = False
        elif not inside:
            clean.append(line)
    if inside:
        raise ValueError("Unclosed Pianissimo hosts marker; restore it manually")
    if expected_owner is not None and owner != str(expected_owner):
        return data
    result = b"".join(clean)
    if domains:
        if result and not result.endswith((b"\n", b"\r")):
            result += b"\r\n"
        records = []
        for domain in sorted(set(domains)):
            valid = normalize_domain(domain)
            if not valid:
                raise ValueError("Invalid website: " + str(domain))
            hosts = {valid} if valid.startswith("www.") else {valid, "www." + valid}
            for host in sorted(hosts):
                records.append(f"0.0.0.0 {host}\r\n::1 {host}\r\n".encode("ascii"))
        result += BEGIN + b" " + str(os.getpid()).encode("ascii") + b"\r\n" + b"".join(records) + END + b"\r\n"
    return result


def write_hosts(domains, path=HOSTS_PATH, expected_owner=None):
    with open(path, "rb") as f:
        original = f.read()
    updated = replace_managed_block(original, domains, expected_owner)
    if updated != original:
        fd, temp = tempfile.mkstemp(prefix="pianissimo-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(updated)
                f.flush()
                os.fsync(f.fileno())
            if os.name == "nt":
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                replace = kernel.ReplaceFileW
                replace.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
                replace.restype = ctypes.c_int
                if not replace(path, temp, None, 0, None, None):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        if os.name == "nt" and os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(HOSTS_PATH)):
            ipconfig = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "ipconfig.exe")
            subprocess.run([ipconfig, "/flushdns"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, check=False)


class WebsiteBlocker:
    def __init__(self, config, scheduler, path=HOSTS_PATH):
        self.config, self.scheduler, self.path = config, scheduler, path
        self.error = None
        self._running = False
        self._thread = None

    def sync(self):
        domains = self.config.data.get("blocked_domains", []) if self.scheduler.is_focus_active() else []
        try:
            write_hosts(domains, self.path)
            self.error = None
        except (OSError, ValueError) as exc:
            self.error = str(exc)

    def start(self):
        self._running = True
        def loop():
            while self._running:
                self.sync()
                time.sleep(1)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()
        write_hosts([], self.path)


def watch_parent(pid, path=HOSTS_PATH):
    """Remove our entries after an unexpected parent exit, including a crash."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if handle:
        kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
        kernel.CloseHandle(handle)
    write_hosts([], path=path, expected_owner=pid)
