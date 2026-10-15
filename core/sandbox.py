from typing import Optional
import re
import os

# Commands that should NEVER be executed by the AI agent
BLOCKED_COMMANDS = [
    # Destructive filesystem operations
    r"\brm\s+(-rf?|--recursive)\s+/",  # rm -rf /
    r"\brm\s+(-rf?|--recursive)\s+~",  # rm -rf ~
    r"\bmkfs\b",                         # format filesystem
    r"\bdd\s+.*of=/dev/",               # disk destroyer
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # fork bomb
    r"\bshutdown\b",                     # shutdown system
    r"\breboot\b",                       # reboot system
    r"\bhalt\b",                         # halt system
    r"\bpoweroff\b",                     # power off
    r"\binit\s+0\b",                     # init 0
    
    # Privilege escalation
    r"\bpasswd\b",                       # change passwords
    r"\busermod\b",                      # modify users
    r"\buserdel\b",                      # delete users
    r"\bchmod\s+777\s+/",               # open permissions on root
    r"\bchown\s+.*\s+/",                # change ownership of root
    
    # Network attacks
    r"\bnmap\b",                         # port scanning
    r"\bnetcat\b|\bnc\s+-",             # netcat reverse shells
    r"\btcpdump\b",                      # packet sniffing
    r"\bwireshark\b",                    # packet capture
    r"\biptables\s+-F\b",               # flush firewall rules
    
    # Crypto / Malware patterns
    r"\bcurl\b.*\|\s*(bash|sh)\b",      # curl pipe to shell
    r"\bwget\b.*\|\s*(bash|sh)\b",      # wget pipe to shell
    r"\bbase64\s+-d\b.*\|\s*(bash|sh)", # base64 decode pipe to shell
    
    # System modification
    r"\bsystemctl\s+(stop|disable)\b",  # stop system services
    r"\bkill\s+-9\s+1\b",              # kill init
    r"\bcrontab\s+-r\b",               # remove all cron jobs
]

# Commands that are safe and commonly needed by an AI agent
ALLOWED_COMMAND_PREFIXES = [
    "echo", "cat", "head", "tail", "ls", "dir", "pwd", "cd",
    "grep", "find", "wc", "sort", "uniq", "cut", "awk", "sed",
    "python", "python3", "pip", "node", "npm", "npx",
    "git", "curl", "wget", "ping",
    "date", "whoami", "hostname", "uname",
    "mkdir", "touch", "cp", "mv",
    "docker", "docker-compose",
    "cargo", "rustc",
    "type", "where", "Get-Content", "Select-String",  # Windows/PowerShell
]


class SandboxResult:
    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason


def validate_command(command: str) -> SandboxResult:
    """
    Validates a shell command against security rules.
    Returns SandboxResult with allowed=True if safe, False if blocked.
    """
    if not command or not command.strip():
        return SandboxResult(False, "Empty command")
    
    stripped = command.strip()
    
    # Check against blocklist patterns
    for pattern in BLOCKED_COMMANDS:
        if re.search(pattern, stripped, re.IGNORECASE):
            return SandboxResult(
                False,
                f"Command blocked by security policy: matches dangerous pattern '{pattern}'"
            )
    
    # Check for suspicious shell chaining that could bypass filters
    # e.g., echo "rm -rf /" | bash
    if re.search(r'\|\s*(bash|sh|zsh|powershell|pwsh)\b', stripped, re.IGNORECASE):
        return SandboxResult(False, "Piping to a shell interpreter is blocked for security")
    
    # Check for eval/exec patterns
    if re.search(r'\beval\b|\bexec\b.*\(', stripped, re.IGNORECASE):
        return SandboxResult(False, "eval/exec patterns are blocked for security")
    
    return SandboxResult(True)


def validate_filepath(filepath: str, allowed_base_dirs: Optional[list] = None) -> SandboxResult:
    """
    Validates a file path to prevent directory traversal and access to sensitive files.
    """
    if not filepath or not filepath.strip():
        return SandboxResult(False, "Empty filepath")
    
    # Normalize path separators and resolve relative components
    norm_path = os.path.normpath(filepath.strip()).replace("\\", "/")
    
    # Block directory traversal attempts
    if ".." in filepath or ".." in norm_path:
        return SandboxResult(False, "Directory traversal (..) is not allowed")
    
    # Canonical resolved path
    try:
        resolved = os.path.realpath(filepath.strip()).replace("\\", "/")
    except Exception:
        return SandboxResult(False, "Invalid or unresolvable filepath")
    
    # Block sensitive system files and directories
    sensitive_patterns = [
        "/etc/passwd", "/etc/shadow", "/etc/sudoers",
        "/.ssh/", "/id_rsa", "/id_ed25519",
        "c:/windows/system32", "c:/windows/syswow64",
        "/proc/", "/sys/",
    ]
    for sensitive in sensitive_patterns:
        if sensitive in norm_path.lower() or sensitive in resolved.lower():
            return SandboxResult(False, f"Access to sensitive path containing '{sensitive}' is blocked")
    
    # If explicit boundary is defined, enforce it
    if allowed_base_dirs:
        matched = False
        for base in allowed_base_dirs:
            base_resolved = os.path.realpath(base).replace("\\", "/")
            if resolved == base_resolved or resolved.startswith(base_resolved.rstrip("/") + "/"):
                matched = True
                break
        if not matched:
            return SandboxResult(False, "Access outside allowed base directories is blocked")
    
    return SandboxResult(True)
