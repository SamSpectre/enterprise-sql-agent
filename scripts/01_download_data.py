"""
Download NYC Taxi Trip Data

This script downloads NYC TLC taxi trip data for the SQL agent project.
We use a subset (10M rows) to keep things manageable locally while still
demonstrating production patterns.

Data Source: NYC Taxi & Limousine Commission
https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
"""

import os
import sys
from pathlib import Path
import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

console = Console()

# NYC TLC Data URLs - Yellow Taxi (most popular)
# Using 2024 data for recency
DATA_URLS = {
    "yellow_tripdata_2024_01": "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet",
    "yellow_tripdata_2024_02": "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-02.parquet",
    "yellow_tripdata_2024_03": "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-03.parquet",
}

# Output directory
DATA_DIR = PROJECT_ROOT / "data" / "raw"


def download_file(url: str, output_path: Path) -> bool:
    """Download a file with progress bar."""
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
            ) as progress:
                task = progress.add_task(f"Downloading {output_path.name}", total=total)
                
                with open(output_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
        
        return True
    except Exception as e:
        console.print(f"[red]Error downloading {url}: {e}[/red]")
        return False


def main():
    """Main download function."""
    console.print("[bold blue]NYC Taxi Data Download Script[/bold blue]")
    console.print("=" * 50)
    
    # Create data directory
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]Data directory: {DATA_DIR}[/green]")
    
    # Download each file
    downloaded = []
    for name, url in DATA_URLS.items():
        output_path = DATA_DIR / f"{name}.parquet"
        
        if output_path.exists():
            console.print(f"[yellow]Skipping {name} - already exists[/yellow]")
            downloaded.append(output_path)
            continue
        
        console.print(f"\n[bold]Downloading {name}...[/bold]")
        if download_file(url, output_path):
            console.print(f"[green]Successfully downloaded: {output_path}[/green]")
            downloaded.append(output_path)
        else:
            console.print(f"[red]Failed to download: {name}[/red]")
    
    # Summary
    console.print("\n" + "=" * 50)
    console.print("[bold]Download Summary[/bold]")
    console.print(f"Files downloaded: {len(downloaded)}/{len(DATA_URLS)}")
    
    # Check file sizes
    total_size = 0
    for path in downloaded:
        size_mb = path.stat().st_size / (1024 * 1024)
        total_size += size_mb
        console.print(f"  {path.name}: {size_mb:.1f} MB")
    
    console.print(f"\n[bold]Total size: {total_size:.1f} MB[/bold]")
    console.print("\n[green]Next step: Run 02_setup_database.py to load data into PostgreSQL[/green]")


if __name__ == "__main__":
    main()
