import os  # noqa: F401
from pathlib import Path
import logging
import datetime
import json
import shutil
import hashlib
import time
import argparse
from rich.console import Console # type: ignore
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn # type: ignore
from rich.panel import Panel # type: ignore
from rich.text import Text # type: ignore  # noqa: F401
from rich.table import Table # type: ignore
from rich import box # type: ignore
from rich.live import Live # type: ignore  # noqa: F401
from rich.align import Align # type: ignore

console = Console()

ASCII_ART = r"""
[cyan]
  ____             _                  _______          _                   
 |  _ \           | |                |__   __|        | |             
 | |_) | __ _  ___| | ___   _ _ __      | | ___   ___ | |    
 |  _ < / _` |/ __| |/ / | | | '_ \     | |/ _ \ / _ \| |    
 | |_) | (_| | (__|   <| |_| | |_) |    | | (_) | (_) | |    
 |____/ \__,_|\___|_|\_\\_,__| .__/     |_|\___/ \___/|_| 
                             | |                                           
 [green]   [white]Made by:[/white] khalil HAMIDANI [/green][cyan]|[red]&[/red]|[/cyan][green] Aymen GHEBRIOU[/green]           
[/cyan]"""
class BackupSystem:
    def __init__(self, source_dir, backup_dir):
        self.source_dir = Path(source_dir).resolve()
        self.backup_dir = Path(backup_dir).resolve()
        self.manifest_file = self.backup_dir / "backup_manifest.json"

        # Create backup directory and parent directories first
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Set up logging to log only to the file
        log_file = self.backup_dir / 'backup.log'
        try:
            # Ensure log file's parent directory exists
            log_file.parent.mkdir(parents=True, exist_ok=True)

            # Create the log file if it doesn't exist
            if not log_file.exists():
                log_file.touch()

            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file.as_posix())  # Only file logging, no console logging
                ]
            )
        except Exception as e:
            # Fallback to console-only logging if file logging fails
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[logging.StreamHandler()]
            )
            print(f"Warning: Could not set up file logging: {str(e)}")
    
        self.logger = logging.getLogger(__name__)

    def setup_logging(log_file_path):
        try:
            # Convert to Path object if not already one
            log_file_path = Path(log_file_path)

            # Ensure the directory for the log file exists
            log_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Initialize logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_file_path.as_posix()),
                    logging.StreamHandler()
                ]
            )
            logging.info("Logging setup complete.")

        except Exception as e:
            # Fallback to console-only logging if file logging fails
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[logging.StreamHandler()]
            )
            print(f"Warning: Could not set up file logging: {e}")
    
    def _load_manifest(self):
        """Load or create backup manifest"""
        try:
            if self.manifest_file.exists():
                with open(self.manifest_file, 'r') as f:
                    return json.load(f)
            return {'backups': []}
        except Exception as e:
            self.logger.error(f"Error loading manifest: {str(e)}")
            return {'backups': []}

    def _save_manifest(self, manifest):
        """Save backup manifest"""
        try:
            with open(self.manifest_file, 'w') as f:
                json.dump(manifest, f, indent=4)
        except Exception as e:
            self.logger.error(f"Error saving manifest: {str(e)}")
            raise

    def _count_files(self):
        """Count total number of files in source directory"""
        return sum(1 for _ in self.source_dir.rglob('*') if _.is_file())

    def _calculate_file_hash(self, filepath):
        """Calculate MD5 hash of a file"""
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    # [Rest of the methods remain the same as in the previous artifact]
    def full_backup(self, progress, task):
        """Perform a full backup with progress tracking"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"full_backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)

        manifest = self._load_manifest()
        file_manifest = {}
        
        total_files = self._count_files()
        progress.update(task, total=total_files)
        
        files_processed = 0
        self.logger.info("Starting full backup...") 
        try:
            for src_file in self.source_dir.rglob('*'):
                if src_file.is_file():
                    rel_path = src_file.relative_to(self.source_dir)
                    dest_file = backup_path / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Update progress description with current file
                    progress.update(task, description=f"[cyan]Backing up: {rel_path}")
                    
                    shutil.copy2(src_file, dest_file)
                    file_manifest[str(rel_path)] = self._calculate_file_hash(src_file)
                    
                    files_processed += 1
                    self.logger.info(f"Backed up file: {src_file}")   
                    progress.update(task, advance=1)
                    
            backup_info = {
                'type': 'full',
                'timestamp': timestamp,
                'path': str(backup_path),
                'files': file_manifest
            }
            manifest['backups'].append(backup_info)
            self._save_manifest(manifest) 
            self.logger.info("Full backup completed successfully") 
            # Update final status
            progress.update(task, description="[bold green]Backup completed successfully!")
            return backup_path, files_processed
            
        except Exception as e:
            progress.update(task, description=f"[bold red]Backup failed: {str(e)}")
            self.logger.error(f"Backup failed: {str(e)}")
            shutil.rmtree(backup_path, ignore_errors=True)
            raise

    def incremental_backup(self, progress, task):
        """Perform an incremental backup with progress tracking."""
        manifest = self._load_manifest()

        # Reference the latest backup (could be full or incremental)
        if not manifest['backups']:
            progress.update(task, description="[bold red]No backup found. Incremental backup skipped.")
            return None, 0

        last_backup = manifest['backups'][-1]
        last_files = last_backup['files']
        new_files = {}

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"incr_backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)

        total_files = self._count_files()
        progress.update(task, total=total_files)

        files_processed = 0
        files_backed_up = 0
        self.logger.info("Starting incremental backup...")

        try:
            for src_file in self.source_dir.rglob('*'):
                if src_file.is_file():
                    rel_path = str(src_file.relative_to(self.source_dir))
                    progress.update(task, description=f"[cyan]Analyzing: {rel_path}")

                    current_hash = self._calculate_file_hash(src_file)
                    files_processed += 1

                    # Backup if the file is new or modified since the last backup
                    if rel_path not in last_files or last_files[rel_path] != current_hash:
                        dest_file = backup_path / rel_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        progress.update(task, description=f"[cyan]Backing up: {rel_path}")
                        shutil.copy2(src_file, dest_file)
                        new_files[rel_path] = current_hash
                        files_backed_up += 1
                        self.logger.info(f"Backed up file: {src_file}")

                    progress.update(task, advance=1)

            # If any files were backed up, save incremental backup info
            if new_files:
                backup_info = {
                    'type': 'incremental',
                    'timestamp': timestamp,
                    'path': str(backup_path),
                    'files': new_files,
                    'parent': last_backup['timestamp']
                }
                manifest['backups'].append(backup_info)
                self._save_manifest(manifest)
                self.logger.info("Incremental backup completed successfully")
                progress.update(task, description=f"[bold green]Backup completed! {files_backed_up} files updated")
                return backup_path, files_backed_up
            else:
                # No changes detected, cleanup created directory
                progress.update(task, description="[bold yellow]No changes detected, backup skipped")
                shutil.rmtree(backup_path)
                return None, 0

        except Exception as e:
            progress.update(task, description=f"[bold red]Backup failed: {str(e)}")
            self.logger.error(f"Backup failed: {str(e)}")
            shutil.rmtree(backup_path, ignore_errors=True)
            raise

    def differential_backup(self, progress, task):
        """Perform a differential backup with progress tracking"""
        manifest = self._load_manifest()
        if not manifest['backups']:
            # return self.full_backup(progress, task)
            progress.update(task, description="[bold red]No full backup found. Differential backup skipped.")
            return None, 0

        # Find last full backup
        last_full = None
        for backup in reversed(manifest['backups']):
            if backup['type'] == 'full':
                last_full = backup
                break

        # if not last_full:
        #     return self.full_backup(progress, task)
        if not last_full:
            progress.update(task, description="[bold yellow]No full backup found. Differential backup skipped.")
            return None, 0

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"diff_backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)

        last_files = last_full['files']
        changed_files = {}
        
        total_files = self._count_files()
        progress.update(task, total=total_files)
        
        files_processed = 0
        files_backed_up = 0
        self.logger.info("Starting differential backup...") 
        try:
            for src_file in self.source_dir.rglob('*'):
                if src_file.is_file():
                    rel_path = str(src_file.relative_to(self.source_dir))
                    progress.update(task, description=f"[cyan]Analyzing: {rel_path}")
                    
                    current_hash = self._calculate_file_hash(src_file)
                    files_processed += 1

                    if rel_path not in last_files or last_files[rel_path] != current_hash:
                        dest_file = backup_path / rel_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        progress.update(task, description=f"[cyan]Backing up: {rel_path}")
                        shutil.copy2(src_file, dest_file)
                        changed_files[rel_path] = current_hash
                        files_backed_up += 1
                        self.logger.info(f"Backed up file: {src_file}") 
                    progress.update(task, advance=1)

            if changed_files:
                backup_info = {
                    'type': 'differential',
                    'timestamp': timestamp,
                    'path': str(backup_path),
                    'files': changed_files,
                    'parent': last_full['timestamp']
                }
                manifest['backups'].append(backup_info)
                self._save_manifest(manifest)
                self.logger.info("differential backup completed successfully") 
                progress.update(task, description=f"[bold green]Backup completed! {files_backed_up} files updated")
                return backup_path, files_backed_up
            else:
                progress.update(task, description="[bold yellow]No changes detected, backup skipped")
                shutil.rmtree(backup_path)
                return None, 0

        except Exception as e:
            progress.update(task, description=f"[bold red]Backup failed: {str(e)}")
            self.logger.error(f"Backup failed: {str(e)}")
            shutil.rmtree(backup_path, ignore_errors=True)
            raise

    def full_backup_call(self):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Initializing full backup...", total=None)
            try:
                backup_path, files_processed = self.full_backup(progress, task)
                time.sleep(1)  # Allow user to see completion message
                console.print(f"\n[green]• Backup location: {backup_path}")
                console.print(f"[green]• Files processed: {files_processed}")
                console.print()
            except Exception as e:
                console.print(f"\n[bold red]✗[/bold red] Backup failed: {str(e)}\n")

    def incremental_backup_call(self):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Analyzing changes...", total=None)
            try:
                result = self.incremental_backup(progress, task)
                time.sleep(1)  # Allow user to see completion message
                if result:
                    backup_path, files_backed_up = result
                    console.print(f"\n[green]• Backup location: {backup_path}")
                    console.print(f"[green]• Files updated: {files_backed_up}")
                console.print()
            except Exception as e:
                console.print(f"\n[bold red]✗[/bold red] Backup failed: {str(e)}\n")

    def differential_backup_call(self):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Calculating differences...", total=None)
            try:
                result = self.differential_backup(progress, task)
                time.sleep(1)  # Allow user to see completion message
                if result:
                    backup_path, files_backed_up = result
                    console.print(f"\n[green]• Backup location: {backup_path}")
                    console.print(f"[green]• Files updated: {files_backed_up}")
        
                console.print()
            except Exception as e:
                console.print(f"\n[bold red]✗[/bold red] Backup failed: {str(e)}\n")

def display_menu():
    console.clear()
    console.print(ASCII_ART)
    
    table = Table(show_header=True, box=box.ROUNDED)
    table.add_column("Option", style="cyan", width=6)
    table.add_column("Description", style="white")
    
    table.add_row("-[1]-", "Full Backup............(Complete system snapshot)")
    table.add_row("-[2]-", "Differential Backup.....(Changes since full backup)")
    table.add_row("-[3]-", "Incremental Backup....(Changes since last backup)")
    table.add_row("-[4]-", "Exit...................(Close the system)")
    
    console.print(Panel(
        Align.center(table),
        title="[bold cyan]Secure Backup System v1.0[/bold cyan]",
        subtitle="[italic]Select an option below[/italic]",
        border_style="cyan",
        width=80
    ))

def typing_effect(text):
    for char in text:
        console.print(char, end='', style="green")
        time.sleep(0.01)
    print()

def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Secure Backup System')
    parser.add_argument('backup_type', type=str, nargs='?', 
                        choices=['1', '2', '3', '4'], 
                        help='Backup type: 1 (Full), 2 (Differential), 3 (Incremental), 4 (Exit)')
    parser.add_argument('-s', '--source', default="/mnt/c/Users/HP/Desktop/backup test/source", 
                        help='Source directory path')
    parser.add_argument('-b', '--backup', default="/mnt/c/Users/HP/Desktop/backup test/backups", 
                        help='Backup directory path')
    return parser.parse_args()

def main():
    # Parse arguments
    args = parse_arguments()
    
    # Initialize backup system with source and backup directories from arguments
    backup_system = BackupSystem(
        source_dir=args.source,
        backup_dir=args.backup
    )

    # If no argument is provided, run interactive mode
    if not args.backup_type:
        with console.screen():
            typing_effect("Initializing secure backup system...")
            time.sleep(0.2)
            typing_effect("Checking system integrity...")
            time.sleep(0.2)
            typing_effect("System ready...")
            time.sleep(0.5)
        
        def wait_for_user():
            console.print("[bold blue]Press enter key to continue...[/bold blue]")
            console.input()
        
        while True:
            display_menu()
            choice = console.input("[bold cyan]Enter your choice (1-4):[/bold cyan] ")

            if choice == "1":
                backup_system.full_backup_call()
                wait_for_user()
            elif choice == "2":
                backup_system.differential_backup_call()
                wait_for_user()
            elif choice == "3":
                backup_system.incremental_backup_call()
                wait_for_user()
            elif choice == "4":
                console.print(Panel.fit(
                    "[bold red]Shutting down backup Tool...[/bold red]",
                    border_style="red"
                ))
                time.sleep(1)
                typing_effect("Thanks for using Secure Backup Tool!")
                typing_effect("Get in touch with us if you have any suggestions.\n")
                console.print("Khalil HAMIDANI: [cyan]Hamidani2002@gmail.com[/cyan]")
                console.print("Aymen GHEBRIOU: [cyan]aymen.ghebriou3@gmail.com[/cyan]")
                break
            else:
                console.print("[bold red]Invalid option. Please try again.[/bold red]\n")
                time.sleep(1.5)
    else:
        # Run backup based on command-line argument
        if args.backup_type == "1":
            backup_system.full_backup_call()
        elif args.backup_type == "2":
            backup_system.differential_backup_call()
        elif args.backup_type == "3":
            backup_system.incremental_backup_call()
        elif args.backup_type == "4":
            console.print(Panel.fit(
                "[bold red]Shutting down backup Tool...[/bold red]",
                border_style="red"
            ))
            typing_effect("Thanks for using Secure Backup Tool!\n")

if __name__ == "__main__":
    main()