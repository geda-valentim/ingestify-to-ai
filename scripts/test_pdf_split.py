#!/usr/bin/env python3
"""
Teste standalone da funcionalidade de divisão de PDF
Não requer Docker ou API rodando
"""

import sys
from pathlib import Path

# Adicionar pasta shared ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.pdf_splitter import PDFSplitter

def test_pdf_split():
    """Testa a divisão do PDF AI-50p.pdf"""

    # Localizar PDF
    pdf_path = Path(__file__).parent.parent / "AI-50p.pdf"

    if not pdf_path.exists():
        print(f"❌ PDF não encontrado: {pdf_path}")
        return False

    print(f"✓ PDF encontrado: {pdf_path}")
    print(f"  Tamanho: {pdf_path.stat().st_size / 1024:.2f} KB\n")

    # Criar splitter
    print("Criando PDFSplitter...")
    temp_dir = Path(__file__).parent.parent / "tmp" / "test_split"
    splitter = PDFSplitter(temp_dir=temp_dir)
    print(f"✓ Diretório temporário: {splitter.temp_dir}\n")

    # Dividir PDF
    print("Dividindo PDF em páginas...")
    print("=" * 60)

    try:
        page_files = splitter.split_pdf(pdf_path)

        print(f"\n✓ PDF dividido com sucesso!")
        print(f"  Total de páginas: {len(page_files)}")
        print(f"\nPáginas criadas:")
        print("-" * 60)

        total_size = 0
        for page_num, page_path in page_files[:10]:  # Mostrar primeiras 10
            size_kb = page_path.stat().st_size / 1024
            total_size += size_kb
            print(f"  Página {page_num:2d}: {page_path.name:20s} ({size_kb:6.2f} KB)")

        if len(page_files) > 10:
            print(f"  ... (+ {len(page_files) - 10} páginas)")

            # Calcular tamanho total
            for page_num, page_path in page_files[10:]:
                total_size += page_path.stat().st_size / 1024

        print("-" * 60)
        print(f"  Tamanho total das páginas: {total_size:.2f} KB")
        print(f"  Tamanho médio por página: {total_size / len(page_files):.2f} KB")

        # Mostrar algumas estatísticas
        print(f"\n📊 Estatísticas:")
        print(f"  PDF original: {pdf_path.stat().st_size / 1024:.2f} KB")
        print(f"  Páginas divididas: {total_size:.2f} KB")
        print(f"  Overhead: {((total_size - pdf_path.stat().st_size / 1024) / (pdf_path.stat().st_size / 1024) * 100):.1f}%")

        # Verificar se primeira e última página existem
        print(f"\n🔍 Verificação:")
        first_page = page_files[0][1]
        last_page = page_files[-1][1]

        print(f"  Primeira página: {first_page.name} ({'✓ existe' if first_page.exists() else '❌ não existe'})")
        print(f"  Última página: {last_page.name} ({'✓ existe' if last_page.exists() else '❌ não existe'})")

        # Cleanup
        print(f"\n🧹 Limpeza:")
        cleanup = input("  Deseja remover arquivos temporários? (s/N): ").strip().lower()
        if cleanup == 's':
            splitter.cleanup_pages(page_files)
            print("  ✓ Arquivos temporários removidos")
            # Remover diretório se vazio
            if splitter.temp_dir.exists() and not any(splitter.temp_dir.iterdir()):
                splitter.temp_dir.rmdir()
                print("  ✓ Diretório temporário removido")
        else:
            print(f"  ℹ Arquivos mantidos em: {splitter.temp_dir}")

        return True

    except Exception as e:
        print(f"\n❌ Erro ao dividir PDF: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Teste de Divisão de PDF - Doc2MD")
    print("=" * 60)
    print()

    success = test_pdf_split()

    print("\n" + "=" * 60)
    if success:
        print("✓ Teste concluído com sucesso!")
    else:
        print("❌ Teste falhou")
    print("=" * 60)
