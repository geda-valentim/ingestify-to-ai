#!/usr/bin/env python3
"""
Script de teste completo: Upload → Split → Conversão
Monitora todo o fluxo sem usar workers do Celery
"""
import sys
import os
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, '/var/app/ingestify-to-ai/backend')

from shared.config import get_settings
from shared.pdf_splitter import should_split_pdf, PDFSplitter
from workers.converter import DoclingConverter
from shared.schemas import JobType

def print_header(text):
    print(f"\n{'='*80}")
    print(f"  {text}")
    print(f"{'='*80}\n")

def print_step(step, text):
    print(f"[STEP {step}] {text}")

def print_info(text):
    print(f"  ℹ️  {text}")

def print_success(text):
    print(f"  ✅ {text}")

def print_error(text):
    print(f"  ❌ {text}")

def print_timing(text, duration):
    print(f"  ⏱️  {text}: {duration:.2f}s")

def test_conversion_flow(pdf_path: str):
    """Testa o fluxo completo de conversão"""

    print_header("TESTE DE CONVERSÃO COMPLETO")
    settings = get_settings()

    # Validate file
    if not os.path.exists(pdf_path):
        print_error(f"Arquivo não encontrado: {pdf_path}")
        return False

    file_size = os.path.getsize(pdf_path) / (1024 * 1024)  # MB
    print_info(f"Arquivo: {pdf_path}")
    print_info(f"Tamanho: {file_size:.2f} MB")
    print_info(f"Timeout configurado: {settings.conversion_timeout_seconds}s")

    # STEP 1: Check if should split
    print_step(1, "Verificando se deve dividir o PDF")
    start = time.time()

    try:
        should_split = should_split_pdf(Path(pdf_path), min_pages=2)
        elapsed = time.time() - start
        print_timing("Verificação de split", elapsed)

        if should_split:
            print_success(f"PDF será dividido em páginas (>= 2 páginas)")
        else:
            print_info(f"PDF será processado como documento único (< 2 páginas)")
    except Exception as e:
        print_error(f"Erro ao verificar split: {e}")
        return False

    # STEP 2: Split PDF (if needed)
    page_files = []
    splitter = None
    if should_split:
        print_step(2, "Dividindo PDF em páginas")
        start = time.time()

        try:
            # Create temp directory
            import tempfile
            temp_dir = Path(tempfile.mkdtemp(prefix="ingestify_test_"))
            print_info(f"Diretório temporário: {temp_dir}")

            # Use PDFSplitter class
            splitter = PDFSplitter(temp_dir)
            page_files = splitter.split_pdf(Path(pdf_path))

            elapsed = time.time() - start
            print_timing("Split do PDF", elapsed)
            print_success(f"PDF dividido em {len(page_files)} páginas")

            for page_num, page_path in page_files:
                page_size = os.path.getsize(page_path) / 1024  # KB
                print_info(f"  Página {page_num}: {page_path} ({page_size:.1f} KB)")

        except Exception as e:
            print_error(f"Erro ao dividir PDF: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print_step(2, "Pulando split (documento único)")

    # STEP 3: Convert pages or whole document
    converter = DoclingConverter()
    results = []

    if should_split and page_files:
        print_step(3, f"Convertendo {len(page_files)} páginas em sequência")

        total_start = time.time()
        for page_num, page_path in page_files:
            print(f"\n  --- Página {page_num}/{len(page_files)} ---")
            page_start = time.time()

            try:
                print_info(f"Convertendo: {os.path.basename(str(page_path))}")

                result = converter.convert_to_markdown(
                    file_path=Path(str(page_path))
                )

                page_elapsed = time.time() - page_start
                print_timing(f"Conversão da página {page_num}", page_elapsed)

                # Check if result has status field or is direct markdown
                if 'status' in result:
                    # Old format with status field
                    if result.get('status') == 'success':
                        markdown_len = len(result.get('markdown', ''))
                        print_success(f"Página {page_num} convertida: {markdown_len} caracteres")
                        results.append({
                            'page': page_num,
                            'markdown': result.get('markdown'),
                            'time': page_elapsed,
                            'status': 'success'
                        })
                    else:
                        error = result.get('error', 'Unknown error')
                        print_error(f"Página {page_num} falhou: {error}")
                        results.append({
                            'page': page_num,
                            'error': error,
                            'time': page_elapsed,
                            'status': 'failed'
                        })
                elif 'markdown' in result:
                    # New format with direct markdown field
                    markdown_len = len(result.get('markdown', ''))
                    print_success(f"Página {page_num} convertida: {markdown_len} caracteres")
                    results.append({
                        'page': page_num,
                        'markdown': result.get('markdown'),
                        'time': page_elapsed,
                        'status': 'success'
                    })
                else:
                    # Unknown format
                    print_error(f"Formato de resposta desconhecido: {result.keys()}")
                    results.append({
                        'page': page_num,
                        'error': f'Unknown response format: {result.keys()}',
                        'time': page_elapsed,
                        'status': 'failed'
                    })

            except Exception as e:
                page_elapsed = time.time() - page_start
                print_error(f"Exceção na página {page_num}: {e}")
                import traceback
                traceback.print_exc()
                results.append({
                    'page': page_num,
                    'error': str(e),
                    'time': page_elapsed,
                    'status': 'error'
                })

        total_elapsed = time.time() - total_start
        print_timing(f"\nConversão total de {len(page_files)} páginas", total_elapsed)

    else:
        print_step(3, "Convertendo documento completo")
        start = time.time()

        try:
            print_info(f"Convertendo: {os.path.basename(pdf_path)}")

            result = converter.convert_to_markdown(
                file_path=Path(pdf_path)
            )

            elapsed = time.time() - start
            print_timing("Conversão do documento", elapsed)

            # Check if result has status field or is direct markdown
            if 'status' in result:
                # Old format with status field
                if result.get('status') == 'success':
                    markdown_len = len(result.get('markdown', ''))
                    print_success(f"Documento convertido: {markdown_len} caracteres")
                    results.append({
                        'markdown': result.get('markdown'),
                        'time': elapsed,
                        'status': 'success'
                    })
                else:
                    error = result.get('error', 'Unknown error')
                    print_error(f"Conversão falhou: {error}")
                    results.append({
                        'error': error,
                        'time': elapsed,
                        'status': 'failed'
                    })
            elif 'markdown' in result:
                # New format with direct markdown field
                markdown_len = len(result.get('markdown', ''))
                print_success(f"Documento convertido: {markdown_len} caracteres")
                results.append({
                    'markdown': result.get('markdown'),
                    'time': elapsed,
                    'status': 'success'
                })
            else:
                # Unknown format
                print_error(f"Formato de resposta desconhecido: {result.keys()}")
                results.append({
                    'error': f'Unknown response format: {result.keys()}',
                    'time': elapsed,
                    'status': 'failed'
                })

        except Exception as e:
            elapsed = time.time() - start
            print_error(f"Exceção na conversão: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                'error': str(e),
                'time': elapsed,
                'status': 'error'
            })

    # STEP 4: Summary
    print_header("RESUMO DOS RESULTADOS")

    successful = [r for r in results if r.get('status') == 'success']
    failed = [r for r in results if r.get('status') in ['failed', 'error']]

    print_info(f"Total de conversões: {len(results)}")
    print_success(f"Sucessos: {len(successful)}")
    if failed:
        print_error(f"Falhas: {len(failed)}")

    if successful:
        total_chars = sum(len(r.get('markdown', '')) for r in successful)
        total_time = sum(r.get('time', 0) for r in results)
        avg_time = total_time / len(results) if results else 0

        print_info(f"Total de caracteres convertidos: {total_chars:,}")
        print_timing("Tempo total", total_time)
        print_timing("Tempo médio por página/documento", avg_time)

    if failed:
        print("\n  Detalhes das falhas:")
        for r in failed:
            page = r.get('page', 'documento')
            error = r.get('error', 'Unknown')
            print(f"    • Página/Doc {page}: {error}")

    # Clean up
    if should_split and splitter and page_files:
        try:
            splitter.cleanup_pages(page_files)
            import shutil
            shutil.rmtree(splitter.temp_dir)
            print_info(f"\nDiretório temporário removido: {splitter.temp_dir}")
        except Exception as e:
            print_error(f"Erro ao remover temp dir: {e}")

    return len(failed) == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_conversion_flow.py <caminho_do_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    success = test_conversion_flow(pdf_path)

    sys.exit(0 if success else 1)
