#!/usr/bin/env python3
"""
Teste de conversão com Docling (sem Docker)
Converte páginas individuais do PDF para markdown
"""

import sys
from pathlib import Path
from datetime import datetime
import time

# Adicionar pasta raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_docling_conversion():
    """Testa conversão de páginas com Docling"""

    print("=" * 80)
    print("TESTE: Conversão de Páginas com Docling")
    print("=" * 80)
    print()

    # Verificar se Docling está instalado
    try:
        from docling.document_converter import DocumentConverter
        print("✓ Docling importado com sucesso")
    except ImportError as e:
        print(f"❌ Docling não está instalado: {e}")
        print()
        print("Para instalar:")
        print("  pip install 'docling>=2.0.0,<3.0.0'")
        return False

    # Verificar se PDFSplitter funciona
    try:
        from backend.shared.pdf_splitter import PDFSplitter
        print("✓ PDFSplitter importado com sucesso")
    except ImportError as e:
        print(f"❌ PDFSplitter não disponível: {e}")
        return False

    print()

    # Localizar PDF
    pdf_path = Path(__file__).parent.parent / "AI-50p.pdf"
    if not pdf_path.exists():
        print(f"❌ PDF não encontrado: {pdf_path}")
        return False

    print(f"✓ PDF encontrado: {pdf_path.name}")
    print(f"  Tamanho: {pdf_path.stat().st_size / 1024:.2f} KB")
    print()

    # Perguntar quantas páginas converter
    try:
        num_pages = int(input("Quantas páginas converter? [1-5]: ") or "3")
        num_pages = max(1, min(num_pages, 5))
    except:
        num_pages = 3

    print()
    print(f"📄 Convertendo {num_pages} primeira(s) página(s)...")
    print()

    # Criar diretório temporário
    temp_dir = Path(__file__).parent.parent / "tmp" / "test_docling"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Dividir PDF
    print("📝 ETAPA 1: Dividindo PDF...")
    splitter = PDFSplitter(temp_dir=temp_dir)

    start_split = time.time()
    page_files = splitter.split_pdf(pdf_path)
    split_time = time.time() - start_split

    print(f"✓ PDF dividido em {len(page_files)} páginas ({split_time:.2f}s)")
    print()

    # Criar conversor Docling com otimizações
    print("📝 ETAPA 2: Inicializando Docling (OTIMIZADO)...")
    start_init = time.time()

    from docling.document_converter import DocumentConverter, PdfFormatOption, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    # Perguntar configurações de otimização
    print()
    print("⚙️  Configurações de performance:")
    enable_ocr = input("  Habilitar OCR (PDFs escaneados)? [s/N]: ").strip().lower() == 's'
    enable_tables = input("  Habilitar estrutura de tabelas? [S/n]: ").strip().lower() != 'n'

    print()
    if not enable_ocr:
        print("  ✅ OCR desabilitado (~10x mais rápido para PDFs digitais)")
    if not enable_tables:
        print("  ✅ Tabelas desabilitadas (mais rápido)")

    # Try to use optimized backend
    backend = None
    backend_name = "default"
    try:
        from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
        backend = DoclingParseDocumentBackend
        backend_name = "DoclingParse (otimizado)"
        print("  ✅ Usando backend otimizado DoclingParse")
    except ImportError:
        try:
            from docling.backend.docling_parse_backend import DoclingParseV2DocumentBackend
            backend = DoclingParseV2DocumentBackend
            backend_name = "DoclingParseV2 (beta, ~10x mais rápido)"
            print("  ✅ Usando backend V2 (beta, ~10x mais rápido)")
        except ImportError:
            print("  ⚠️  Usando backend padrão (backends otimizados não disponíveis)")

    print()

    # Pipeline otimizado
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = enable_ocr
    pipeline_options.do_table_structure = enable_tables

    if backend:
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=backend
                )
            }
        )
    else:
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )

    init_time = time.time() - start_init
    print(f"✓ Docling inicializado (OCR={enable_ocr}, Tables={enable_tables}, Backend={backend_name}) ({init_time:.2f}s)")
    print()

    # Converter páginas
    print("📝 ETAPA 3: Convertendo páginas para markdown...")
    print("-" * 80)

    results = []
    total_conversion_time = 0

    for i in range(min(num_pages, len(page_files))):
        page_num, page_path = page_files[i]

        print(f"\nPágina {page_num}:")
        print(f"  Arquivo: {page_path.name}")
        print(f"  Tamanho: {page_path.stat().st_size / 1024:.2f} KB")

        # Converter
        start_conv = time.time()

        try:
            result = converter.convert(str(page_path))
            markdown = result.document.export_to_markdown()

            conv_time = time.time() - start_conv
            total_conversion_time += conv_time

            # Estatísticas
            lines = markdown.count('\n') + 1
            chars = len(markdown)
            words = len(markdown.split())

            print(f"  ✓ Convertido em {conv_time:.2f}s")
            print(f"  Markdown: {lines} linhas, {words} palavras, {chars} caracteres")

            # Preview
            preview = markdown[:200].replace('\n', ' ')
            if len(preview) == 200:
                preview += "..."
            print(f"  Preview: {preview}")

            results.append({
                'page_num': page_num,
                'page_path': page_path,
                'markdown': markdown,
                'conversion_time': conv_time,
                'lines': lines,
                'words': words,
                'chars': chars,
            })

        except Exception as e:
            print(f"  ❌ Erro na conversão: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("-" * 80)

    # Estatísticas finais
    print()
    print("=" * 80)
    print("ESTATÍSTICAS FINAIS")
    print("=" * 80)
    print()

    print(f"📊 Resumo:")
    print(f"  Páginas processadas: {len(results)}/{num_pages}")
    print(f"  Tempo total: {split_time + init_time + total_conversion_time:.2f}s")
    print(f"    • Split: {split_time:.2f}s")
    print(f"    • Init Docling: {init_time:.2f}s")
    print(f"    • Conversão: {total_conversion_time:.2f}s")
    print()

    if results:
        avg_time = total_conversion_time / len(results)
        total_words = sum(r['words'] for r in results)
        total_chars = sum(r['chars'] for r in results)

        print(f"📈 Performance:")
        print(f"  Tempo médio por página: {avg_time:.2f}s")
        print(f"  Velocidade: {60/avg_time:.1f} páginas/minuto")
        print()

        print(f"📝 Conteúdo extraído:")
        print(f"  Total de palavras: {total_words}")
        print(f"  Total de caracteres: {total_chars}")
        print(f"  Média de palavras/página: {total_words/len(results):.0f}")
        print()

        # Mostrar primeira conversão completa
        print("=" * 80)
        print(f"EXEMPLO: Markdown da Página {results[0]['page_num']} (completo)")
        print("=" * 80)
        print()
        print(results[0]['markdown'][:1000])
        if len(results[0]['markdown']) > 1000:
            print("\n... (truncado)")
        print()

    # Perguntar se quer salvar
    save = input("Deseja salvar os resultados em arquivos? [s/N]: ").strip().lower()

    if save == 's':
        output_dir = Path(__file__).parent.parent / "tmp" / "test_docling_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Salvar páginas individuais
        for result in results:
            output_file = output_dir / f"page_{result['page_num']:04d}.md"

            # Adicionar metadados ao markdown
            md_content = f"""<!-- Metadata
Page: {result['page_num']}
Lines: {result['lines']}
Words: {result['words']}
Chars: {result['chars']}
Conversion Time: {result['conversion_time']:.2f}s
-->

{result['markdown']}
"""

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(md_content)
            print(f"✓ Salvo: {output_file}")

        # Salvar documento completo (merged)
        merged_file = output_dir / "complete_document.md"
        with open(merged_file, 'w', encoding='utf-8') as f:
            # Cabeçalho
            f.write(f"""# Documento Completo - {pdf_path.name}

**Páginas processadas:** {len(results)}
**Total de palavras:** {sum(r['words'] for r in results)}
**Tempo total de conversão:** {total_conversion_time:.2f}s
**Configuração:** OCR={enable_ocr}, Tables={enable_tables}

---

""")

            # Conteúdo de cada página
            for i, result in enumerate(results):
                f.write(f"\n\n<!-- Página {result['page_num']} -->\n\n")
                f.write(result['markdown'])

                # Separador entre páginas (exceto última)
                if i < len(results) - 1:
                    f.write("\n\n---\n\n")

        print(f"✓ Salvo documento completo: {merged_file}")
        print()
        print(f"📁 Resultados salvos em: {output_dir}")
        print(f"   • {len(results)} páginas individuais")
        print(f"   • 1 documento completo (merged)")
        print()

    # Cleanup
    cleanup = input("Deseja remover arquivos temporários de páginas? [s/N]: ").strip().lower()

    if cleanup == 's':
        splitter.cleanup_pages(page_files)
        if temp_dir.exists() and not any(temp_dir.iterdir()):
            temp_dir.rmdir()
        print("✓ Arquivos temporários removidos")
    else:
        print(f"ℹ Arquivos mantidos em: {temp_dir}")

    print()
    print("=" * 80)
    print("✅ TESTE CONCLUÍDO!")
    print("=" * 80)
    print()

    if results:
        avg_time_per_page = total_conversion_time / len(results)

        print("🎯 Conclusões:")
        print(f"  • Docling está funcionando corretamente ✓")
        print(f"  • Conversão de {len(results)} página(s): OK ✓")
        print(f"  • Tempo médio: {avg_time_per_page:.2f}s por página")
        print(f"  • Velocidade: {60/avg_time_per_page:.1f} páginas/minuto")
        print()

        # Estimativas
        print("📊 Estimativas para diferentes cenários:")
        print(f"  • PDF de 10 páginas: ~{avg_time_per_page*10:.0f}s ({avg_time_per_page*10/60:.1f} min)")
        print(f"  • PDF de 50 páginas: ~{avg_time_per_page*50:.0f}s ({avg_time_per_page*50/60:.1f} min)")
        print(f"  • PDF de 100 páginas: ~{avg_time_per_page*100:.0f}s ({avg_time_per_page*100/60:.1f} min)")
        print()

        # Speedup comparado com configurações não otimizadas
        print("⚡ Performance vs configurações padrão:")
        if not enable_ocr:
            print("  • OCR desabilitado: ~10x mais rápido")
            print(f"    (Sem otimização: ~{avg_time_per_page*10:.1f}s/página)")
        if not enable_tables:
            print("  • Tabelas desabilitadas: ~2x mais rápido")
        print("  • Backend V2: ~10x mais rápido no parsing")
        print()

        print("🚀 Próximos passos:")
        print("  1. Processamento paralelo com Celery workers")
        print("     → Com 5 workers: ~{:.0f}x speedup adicional".format(5))
        print(f"     → 100 páginas em ~{avg_time_per_page*100/5:.0f}s ({avg_time_per_page*100/5/60:.1f} min)")
        print()
        print("  2. Ajustar configurações conforme tipo de documento:")
        print("     → PDFs digitais: OCR=False, Tables=True")
        print("     → PDFs escaneados: OCR=True, Tables=True")
        print("     → Documentos simples: OCR=False, Tables=False")
        print()
        return True
    else:
        print("❌ Nenhuma página foi convertida com sucesso")
        return False

if __name__ == "__main__":
    try:
        success = test_docling_conversion()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Teste interrompido pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
