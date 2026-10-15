import unittest
import os
import sys

# Ensure root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sandbox import validate_command, validate_filepath


class TestSandboxValidation(unittest.TestCase):
    def test_empty_command(self):
        res = validate_command("")
        self.assertFalse(res.allowed)

    def test_blocked_destructive_commands(self):
        blocked = [
            "rm -rf /",
            "rm -rf ~",
            "mkfs /dev/sda1",
            "shutdown -h now",
            ":(){ :|:& };:",
            "echo 'evil' | bash",
            "eval('malicious()')",
        ]
        for cmd in blocked:
            res = validate_command(cmd)
            self.assertFalse(res.allowed, f"Expected '{cmd}' to be blocked")

    def test_allowed_commands(self):
        allowed = [
            "ls -la",
            "echo 'Hello World'",
            "python --version",
            "git status",
            "cargo test",
            "cat README.md",
        ]
        for cmd in allowed:
            res = validate_command(cmd)
            self.assertTrue(res.allowed, f"Expected '{cmd}' to be allowed")

    def test_filepath_traversal(self):
        blocked_paths = [
            "../secret.txt",
            "..\\config.json",
            "nested/../../etc/passwd",
            "/etc/passwd",
            "C:\\Windows\\System32\\cmd.exe",
        ]
        for path in blocked_paths:
            res = validate_filepath(path)
            self.assertFalse(res.allowed, f"Expected '{path}' to be blocked")

    def test_filepath_boundary(self):
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        valid_file = os.path.join(curr_dir, "test_sandbox.py")
        res = validate_filepath(valid_file, allowed_base_dirs=[curr_dir])
        self.assertTrue(res.allowed)

        # File outside boundary should be blocked
        res_outside = validate_filepath("C:/outside/file.txt", allowed_base_dirs=[curr_dir])
        self.assertFalse(res_outside.allowed)


if __name__ == "__main__":
    unittest.main()
