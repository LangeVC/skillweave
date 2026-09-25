import os
import subprocess
import signal
from typing import List, Dict, Optional, Tuple

class ProcessLimitExceeded(Exception):
    pass

def redact_secrets(text: str, secrets: List[str]) -> str:
    """Redact secret strings from text."""
    if not text:
        return text
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***REDACTED***")
    return text

def run_process(
    cmd: List[str],
    env_allowlist: Optional[List[str]] = None,
    extra_env: Optional[Dict[str, str]] = None,
    secrets: Optional[List[str]] = None,
    output_limit_bytes: int = 1024 * 1024, # 1MB limit by default
) -> Tuple[int, str, str]:
    """
    Run a process with environment allowlist, secret redaction, and output limits.
    Returns (returncode, stdout, stderr).
    """
    secrets = secrets or []
    
    # 1. Environment allowlist
    env = {}
    if env_allowlist is not None:
        for key in env_allowlist:
            if key in os.environ:
                env[key] = os.environ[key]
    else:
        env = os.environ.copy()
        
    if extra_env:
        env.update(extra_env)
        
    # Start process
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False # read as bytes for exact limit
    )
    
    stdout_chunks = []
    stderr_chunks = []
    total_bytes = 0
    
    import select
    
    # 3. Output/artifact limits and read incrementally
    try:
        while True:
            reads = [proc.stdout, proc.stderr]
            reads = [r for r in reads if r is not None]
            if not reads:
                break
                
            ret = select.select(reads, [], [], 0.1)
            for fd in ret[0]:
                chunk = os.read(fd.fileno(), 4096)
                if not chunk:
                    if fd == proc.stdout:
                        proc.stdout = None
                    else:
                        proc.stderr = None
                    continue
                    
                total_bytes += len(chunk)
                if fd == proc.stdout:
                    stdout_chunks.append(chunk)
                else:
                    stderr_chunks.append(chunk)
                    
                if total_bytes > output_limit_bytes:
                    proc.kill()
                    raise ProcessLimitExceeded(f"Output limit of {output_limit_bytes} bytes exceeded")
            
            if proc.poll() is not None:
                # Read remaining
                if proc.stdout:
                    chunk = proc.stdout.read()
                    if chunk:
                        stdout_chunks.append(chunk)
                        total_bytes += len(chunk)
                if proc.stderr:
                    chunk = proc.stderr.read()
                    if chunk:
                        stderr_chunks.append(chunk)
                        total_bytes += len(chunk)
                        
                if total_bytes > output_limit_bytes:
                    proc.kill()
                    raise ProcessLimitExceeded(f"Output limit of {output_limit_bytes} bytes exceeded")
                break
                
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
            
    stdout_str = b"".join(stdout_chunks).decode("utf-8", errors="replace")
    stderr_str = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    
    # 2. Secret redaction
    stdout_str = redact_secrets(stdout_str, secrets)
    stderr_str = redact_secrets(stderr_str, secrets)
    
    return proc.returncode, stdout_str, stderr_str
