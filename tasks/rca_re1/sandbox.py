"""Linux candidate access boundary; no root, containers, or upstream changes."""
import ctypes
import errno
import os
import platform
from pathlib import Path


def restrict(read_paths, write_paths):
    """Landlock filesystem allowlist plus seccomp network/process-memory denial.

    Fail closed when unsupported. Applied before importing candidate code.
    """
    libc = ctypes.CDLL(None, use_errno=True)

    def check(value):
        if value < 0:
            raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
        return value

    abi = check(libc.syscall(444, 0, 0, 1))
    if abi < 3:
        raise RuntimeError("Landlock ABI >=3 required")
    # EXECUTE through REFER (ABI 2), TRUNCATE (ABI 3).
    handled = (1 << 15) - 1

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    ruleset = Ruleset(handled)
    fd = check(libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0))
    read_access = (1 << 0) | (1 << 2) | (1 << 3)
    try:
        for raw, writable in [(p, False) for p in read_paths] + [(p, True) for p in write_paths]:
            path = Path(raw).resolve()
            if not path.exists():
                continue
            access = handled if writable else read_access
            if not path.is_dir():
                access &= (1 << 0) | (1 << 1) | (1 << 2) | (1 << 14)
            parent = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(access, parent)
                check(libc.syscall(445, fd, 1, ctypes.byref(rule), 0))
            finally:
                os.close(parent)
        check(libc.prctl(38, 1, 0, 0, 0))  # PR_SET_NO_NEW_PRIVS
        check(libc.syscall(446, fd, 0))
    finally:
        os.close(fd)

    restrict_network()


def restrict_network():
    """Deny IP sockets and connections; also usable inside a GPU container."""
    libc = ctypes.CDLL(None, use_errno=True)
    def check(value):
        if value < 0:
            raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
        return value
    check(libc.prctl(38, 1, 0, 0, 0))
    machine = platform.machine()
    denied = {
        "aarch64": [199, 203, 117, 270, 271, 438],
        "x86_64": [53, 42, 101, 310, 311, 438],
    }.get(machine)
    if denied is None:
        raise RuntimeError(f"Unsupported seccomp architecture: {machine}")

    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                    ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]

    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

    # Check audit architecture too, preventing syscall-number ABI bypasses.
    arch = {"aarch64": 0xC00000B7, "x86_64": 0xC000003E}[machine]
    instructions = [Filter(0x20, 0, 0, 4), Filter(0x15, 1, 0, arch),
                    Filter(0x06, 0, 0, 0x80000000), Filter(0x20, 0, 0, 0)]
    # CUDA opens an AF_UNIX socket for local driver operations. Permit creation
    # only for AF_UNIX; connect remains denied, as do all IP socket families.
    socket_syscall = {"aarch64": 198, "x86_64": 41}[machine]
    instructions += [Filter(0x15, 0, 4, socket_syscall), Filter(0x20, 0, 0, 16),
                     Filter(0x15, 0, 1, 1), Filter(0x06, 0, 0, 0x7FFF0000),
                     Filter(0x06, 0, 0, 0x00050000 | errno.EPERM)]
    for syscall in denied:
        instructions += [Filter(0x15, 0, 1, syscall),
                         Filter(0x06, 0, 0, 0x00050000 | errno.EPERM)]
    # x32 calls must not bypass x86_64 syscall numbers.
    if machine == "x86_64":
        instructions += [Filter(0x45, 0, 1, 0x40000000),
                         Filter(0x06, 0, 0, 0x00050000 | errno.EPERM)]
    instructions.append(Filter(0x06, 0, 0, 0x7FFF0000))
    filters = (Filter * len(instructions))(*instructions)
    program = Program(len(instructions), filters)
    check(libc.prctl(22, 2, ctypes.byref(program), 0, 0))  # SECCOMP_MODE_FILTER
