#!/usr/bin/env python3
"""
Comprehensive Conversion Monitoring Script

Tests PDF conversion with full monitoring:
- Upload via API key authentication
- Real-time job status polling
- Per-page progress tracking
- Worker log monitoring
- Performance metrics collection
- Detailed report generation
"""

import sys
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import requests

# Configuration
API_URL = "http://localhost:8000"
API_KEY = "doc2md_sk_uu7rQmvJGsOmYUG6QPz41vntpeV71WDb7WwsyxA1NiQ"

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str):
    """Print section header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")


def print_info(label: str, value: str):
    """Print info line"""
    print(f"{Colors.CYAN}  ℹ️  {label}:{Colors.ENDC} {value}")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}  ✅ {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}  ⚠️  {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}  ❌ {text}{Colors.ENDC}")


def print_timer(label: str, seconds: float):
    """Print timing info"""
    print(f"{Colors.BLUE}  ⏱️  {label}:{Colors.ENDC} {seconds:.2f}s")


def upload_pdf(pdf_path: Path) -> Optional[str]:
    """
    Upload PDF using API key authentication

    Returns:
        job_id if successful, None otherwise
    """
    print_header("UPLOADING PDF")

    if not pdf_path.exists():
        print_error(f"File not found: {pdf_path}")
        return None

    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
    print_info("File", str(pdf_path))
    print_info("Size", f"{file_size_mb:.2f} MB")

    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path.name, f, 'application/pdf')}
            data = {'source_type': 'file'}
            headers = {'X-API-Key': API_KEY}

            start_time = time.time()
            response = requests.post(
                f"{API_URL}/upload",
                files=files,
                data=data,
                headers=headers
            )
            upload_time = time.time() - start_time

            if response.status_code in [200, 201]:
                result = response.json()
                job_id = result.get('job_id')
                print_success(f"Upload successful! Job ID: {job_id}")
                print_timer("Upload time", upload_time)
                return job_id
            else:
                print_error(f"Upload failed: {response.status_code}")
                print(response.text)
                return None

    except Exception as e:
        print_error(f"Upload error: {str(e)}")
        return None


def get_job_status(job_id: str) -> Optional[Dict]:
    """Get job status from API"""
    try:
        headers = {'X-API-Key': API_KEY}
        response = requests.get(
            f"{API_URL}/jobs/{job_id}",
            headers=headers
        )

        if response.status_code == 200:
            return response.json()
        else:
            return None

    except Exception as e:
        print_error(f"Status check error: {str(e)}")
        return None


def get_worker_logs(last_n_lines: int = 20) -> List[str]:
    """Get recent worker logs"""
    try:
        result = subprocess.run(
            ['docker', 'compose', 'logs', '--tail', str(last_n_lines), 'worker'],
            capture_output=True,
            text=True,
            cwd='/var/app/ingestify-to-ai'
        )
        return result.stdout.split('\n') if result.returncode == 0 else []
    except Exception:
        return []


def monitor_conversion(job_id: str, pdf_name: str) -> Dict:
    """
    Monitor conversion with full metrics

    Returns:
        Dictionary with monitoring results
    """
    print_header(f"MONITORING CONVERSION: {pdf_name}")

    start_time = time.time()
    last_progress = 0
    last_log_check = time.time()
    page_timings = []
    status_history = []

    poll_interval = 2  # seconds
    log_check_interval = 5  # seconds

    while True:
        # Get current status
        status = get_job_status(job_id)

        if not status:
            print_warning("Could not fetch job status, retrying...")
            time.sleep(poll_interval)
            continue

        current_time = time.time()
        elapsed = current_time - start_time

        # Record status
        status_history.append({
            'timestamp': current_time,
            'status': status.get('status'),
            'progress': status.get('progress', 0),
            'elapsed': elapsed
        })

        current_status = status.get('status')
        current_progress = status.get('progress', 0)

        # Print status update
        if current_progress != last_progress:
            print(f"\r{Colors.CYAN}[{elapsed:.1f}s] Status: {current_status} | Progress: {current_progress}%{Colors.ENDC}", end='', flush=True)
            last_progress = current_progress

        # Check for page-level progress
        if status.get('total_pages'):
            total_pages = status['total_pages']
            pages_completed = status.get('pages_completed', 0)
            pages_failed = status.get('pages_failed', 0)

            # Calculate per-page timing
            if pages_completed > len(page_timings):
                page_time = elapsed / pages_completed if pages_completed > 0 else 0
                page_timings.append(page_time)
                print(f"\n{Colors.GREEN}  📄 Page {pages_completed}/{total_pages} completed (avg: {page_time:.2f}s/page){Colors.ENDC}")

        # Check worker logs periodically
        if current_time - last_log_check > log_check_interval:
            logs = get_worker_logs(last_n_lines=10)
            errors = [line for line in logs if 'ERROR' in line or 'FAILED' in line]
            if errors:
                print(f"\n{Colors.YELLOW}  Recent errors in worker logs:{Colors.ENDC}")
                for error in errors[-3:]:  # Show last 3 errors
                    print(f"    {error[:100]}")
            last_log_check = current_time

        # Check if done
        if current_status in ['completed', 'failed']:
            print()  # New line after progress
            break

        time.sleep(poll_interval)

    total_time = time.time() - start_time

    # Final status
    final_status = status.get('status')
    if final_status == 'completed':
        print_success(f"Conversion completed in {total_time:.2f}s")
    else:
        print_error(f"Conversion failed after {total_time:.2f}s")
        error_msg = status.get('error', 'Unknown error')
        print_error(f"Error: {error_msg}")

    return {
        'job_id': job_id,
        'pdf_name': pdf_name,
        'status': final_status,
        'total_time': total_time,
        'total_pages': status.get('total_pages'),
        'pages_completed': status.get('pages_completed', 0),
        'pages_failed': status.get('pages_failed', 0),
        'page_timings': page_timings,
        'status_history': status_history,
        'final_progress': status.get('progress', 0)
    }


def get_conversion_result(job_id: str) -> Optional[Dict]:
    """Get final conversion result"""
    try:
        headers = {'X-API-Key': API_KEY}
        response = requests.get(
            f"{API_URL}/jobs/{job_id}/result",
            headers=headers
        )

        if response.status_code == 200:
            return response.json()
        else:
            return None

    except Exception as e:
        print_error(f"Result fetch error: {str(e)}")
        return None


def generate_report(results: List[Dict]):
    """Generate comprehensive performance report"""
    print_header("PERFORMANCE REPORT")

    # Summary table
    print(f"{Colors.BOLD}File Conversion Summary:{Colors.ENDC}\n")
    print(f"{'PDF Name':<40} {'Status':<12} {'Time':<10} {'Pages':<8} {'Avg/Page':<12} {'Chars':<10}")
    print("-" * 92)

    for result in results:
        pdf_name = result['pdf_name']
        status = result['status']
        total_time = result['total_time']
        total_pages = result['total_pages'] or 1
        pages_completed = result['pages_completed']

        # Calculate average time per page
        pages_completed = pages_completed or 1
        avg_per_page = total_time / pages_completed

        # Get result length
        conversion_result = result.get('conversion_result')
        chars = len(conversion_result.get('markdown', '')) if conversion_result else 0

        status_icon = "✅" if status == "completed" else "❌"
        print(f"{pdf_name[:39]:<40} {status_icon} {status:<10} {total_time:>8.2f}s {pages_completed}/{total_pages:<5} {avg_per_page:>10.2f}s {chars:>10}")

    print()

    # Detailed metrics
    print(f"\n{Colors.BOLD}Detailed Metrics:{Colors.ENDC}\n")

    for result in results:
        print(f"{Colors.CYAN}📁 {result['pdf_name']}{Colors.ENDC}")
        print(f"   Job ID: {result['job_id']}")
        print(f"   Status: {result['status']}")
        print(f"   Total Time: {result['total_time']:.2f}s")
        print(f"   Pages: {result['pages_completed']}/{result['total_pages'] or 1}")

        if result['page_timings']:
            avg_timing = sum(result['page_timings']) / len(result['page_timings'])
            min_timing = min(result['page_timings'])
            max_timing = max(result['page_timings'])
            print(f"   Page Timing: avg={avg_timing:.2f}s, min={min_timing:.2f}s, max={max_timing:.2f}s")

        if result.get('conversion_result'):
            conv_result = result['conversion_result']
            markdown_len = len(conv_result.get('markdown', ''))
            print(f"   Output Length: {markdown_len} characters")
            print(f"   Words: {markdown_len // 6:.0f} (estimated)")

        print()

    # Configuration impact
    print(f"\n{Colors.BOLD}Configuration Impact:{Colors.ENDC}\n")
    print(f"  Current Docling Settings:")
    print(f"    - OCR: {Colors.RED}Disabled{Colors.ENDC} (faster for digital PDFs)")
    print(f"    - Tables: {Colors.GREEN}Enabled{Colors.ENDC} (structure recognition)")
    print(f"    - Images: {Colors.RED}Disabled{Colors.ENDC} (text-only, faster)")
    print(f"    - Backend: DoclingParseV2 (optimized)")

    print(f"\n  {Colors.YELLOW}Performance Impact Estimates:{Colors.ENDC}")
    print(f"    - Enabling OCR: ~10x slower (only for scanned docs)")
    print(f"    - Enabling Images: ~2-3x slower (image extraction)")
    print(f"    - Disabling Tables: ~20% faster (no structure parsing)")


def main():
    """Main execution"""
    if len(sys.argv) < 2:
        print("Usage: python test_conversion_monitor.py <pdf_file1> [pdf_file2] ...")
        sys.exit(1)

    pdf_files = [Path(arg) for arg in sys.argv[1:]]
    results = []

    print_header("DOCLING CONVERSION TESTING & MONITORING")
    print_info("API URL", API_URL)
    print_info("Files to test", ", ".join([p.name for p in pdf_files]))
    print_info("API Key", f"{API_KEY[:20]}...")

    for pdf_path in pdf_files:
        # Upload
        job_id = upload_pdf(pdf_path)
        if not job_id:
            print_error(f"Skipping {pdf_path.name} due to upload failure")
            continue

        # Monitor
        result = monitor_conversion(job_id, pdf_path.name)

        # Get final result
        print("\nFetching conversion result...")
        conversion_result = get_conversion_result(job_id)
        result['conversion_result'] = conversion_result

        if conversion_result:
            markdown_len = len(conversion_result.get('markdown', ''))
            print_success(f"Retrieved result: {markdown_len} characters")

        results.append(result)

        # Small delay between files
        if pdf_path != pdf_files[-1]:
            print("\nWaiting 3 seconds before next file...\n")
            time.sleep(3)

    # Generate report
    if results:
        generate_report(results)

    print_header("TESTING COMPLETE")


if __name__ == "__main__":
    main()
