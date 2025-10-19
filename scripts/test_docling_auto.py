#!/usr/bin/env python3
"""
Automated test for Docling conversion (no user input required)
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.shared.pdf_splitter import PDFSplitter
from backend.workers.converter import DoclingConverter

def main():
    print("=" * 80)
    print("AUTOMATED DOCLING CONVERSION TEST")
    print("=" * 80)
    print()

    # Test PDF path
    pdf_path = project_root / "AI-50p.pdf"

    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        sys.exit(1)

    print(f"✓ PDF found: {pdf_path.name}")
    print(f"  Size: {pdf_path.stat().st_size / 1024:.2f} KB")
    print()

    # Test 1: PDF Splitting
    print("Test 1: PDF Splitting")
    print("-" * 40)
    try:
        output_dir = project_root / "temp_test_pages"
        output_dir.mkdir(exist_ok=True)

        splitter = PDFSplitter(output_dir)
        page_files = splitter.split_pdf(pdf_path)
        print(f"✓ Split {len(page_files)} pages successfully")

        # Clean up
        for page_num, page_file in page_files:
            if os.path.exists(page_file):
                os.remove(page_file)
        output_dir.rmdir()

    except Exception as e:
        print(f"❌ PDF splitting failed: {e}")
        sys.exit(1)

    print()

    # Test 2: Single Page Conversion
    print("Test 2: Converting first page only")
    print("-" * 40)
    try:
        # Split just first page
        output_dir = project_root / "temp_test_single"
        output_dir.mkdir(exist_ok=True)

        splitter = PDFSplitter(output_dir)
        page_files = splitter.split_pdf(pdf_path)
        page_num, first_page = page_files[0]

        print(f"✓ Extracted page {page_num}: {Path(first_page).name}")
        print(f"  Converting to markdown...")

        # Convert
        converter = DoclingConverter()
        result = converter.convert_to_markdown(Path(first_page))

        print(f"✓ Conversion successful!")
        print(f"  Markdown length: {len(result['markdown'])} characters")
        print(f"  Has content: {len(result['markdown']) > 100}")

        # Show preview
        preview = result['markdown'][:500].replace("\n", "\n  ")
        print(f"\n  Preview (first 500 chars):")
        print(f"  {preview}...")

        # Clean up
        for _, page_file in page_files:
            if os.path.exists(page_file):
                os.remove(page_file)
        output_dir.rmdir()

        print()
        print("=" * 80)
        print("✓ ALL TESTS PASSED")
        print("=" * 80)

    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
