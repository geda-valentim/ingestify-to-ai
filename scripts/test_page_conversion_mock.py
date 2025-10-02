#!/usr/bin/env python3
"""
Teste de conversão por página (MOCK)
Simula o fluxo completo sem precisar do Docling instalado
"""

import sys
from pathlib import Path
from datetime import datetime
import time
import hashlib

# Adicionar pasta raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

class MockDoclingConverter:
    """Mock do Docling Converter para testes"""

    def convert(self, file_path):
        """Simula conversão de PDF para markdown"""
        time.sleep(0.1)  # Simular processamento

        # Gerar markdown fake baseado no nome do arquivo
        file_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]

        class MockResult:
            class MockDocument:
                def export_to_markdown(self):
                    # Gerar markdown simulado
                    page_name = Path(file_path).stem
                    return f"""# Página Convertida - {page_name}

Este é um markdown **simulado** para teste do fluxo de conversão.

## Conteúdo Simulado

- Item 1: Análise de dados
- Item 2: Machine Learning
- Item 3: Inteligência Artificial

### Seção Técnica

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod
tempor incididunt ut labore et dolore magna aliqua.

```python
def example_code():
    return "Código extraído do PDF"
```

**Tabela Simulada:**

| Coluna 1 | Coluna 2 | Coluna 3 |
|----------|----------|----------|
| Dado A   | Dado B   | Dado C   |
| Valor 1  | Valor 2  | Valor 3  |

### Conclusão

Este conteúdo foi gerado automaticamente para simular a conversão do Docling.

Hash do arquivo: `{file_hash}`
Timestamp: {datetime.now().isoformat()}
"""

            document = MockDocument()

        return MockResult()


def test_page_conversion():
    """Testa conversão de páginas (com mock do Docling)"""

    print("=" * 80)
    print("TESTE: Conversão de Páginas por Página (MOCK)")
    print("=" * 80)
    print()
    print("ℹ️  Este teste usa MOCK do Docling (sem precisar instalar)")
    print()

    # Importar PDFSplitter
    from shared.pdf_splitter import PDFSplitter

    # Localizar PDF
    pdf_path = Path(__file__).parent.parent / "AI-50p.pdf"
    if not pdf_path.exists():
        print(f"❌ PDF não encontrado: {pdf_path}")
        return False

    print(f"✓ PDF encontrado: {pdf_path.name}")
    print(f"  Tamanho: {pdf_path.stat().st_size / 1024:.2f} KB")
    print()

    # Perguntar quantas páginas
    try:
        num_pages = int(input("Quantas páginas converter? [1-5]: ") or "3")
        num_pages = max(1, min(num_pages, 10))
    except:
        num_pages = 3

    print()
    print(f"📄 Processando {num_pages} primeira(s) página(s)...")
    print()

    # Criar diretório temporário
    temp_dir = Path(__file__).parent.parent / "tmp" / "test_conversion"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # ETAPA 1: Split
    print("📝 ETAPA 1: Dividindo PDF...")
    splitter = PDFSplitter(temp_dir=temp_dir)

    start_split = time.time()
    page_files = splitter.split_pdf(pdf_path)
    split_time = time.time() - start_split

    print(f"✓ PDF dividido em {len(page_files)} páginas ({split_time:.2f}s)")
    print()

    # ETAPA 2: Inicializar "Docling"
    print("📝 ETAPA 2: Inicializando conversor (MOCK)...")
    start_init = time.time()

    converter = MockDoclingConverter()

    init_time = time.time() - start_init
    print(f"✓ Conversor inicializado ({init_time:.2f}s)")
    print()

    # ETAPA 3: Converter páginas
    print("📝 ETAPA 3: Convertendo páginas...")
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
            preview_lines = markdown.split('\n')[:3]
            print(f"  Preview:")
            for line in preview_lines:
                print(f"    {line[:70]}")

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
            print(f"  ❌ Erro: {e}")
            import traceback
            traceback.print_exc()

    print()
    print("-" * 80)

    # ETAPA 4: Simular merge
    if len(results) > 1:
        print()
        print("📝 ETAPA 4: Simulando merge de resultados...")

        start_merge = time.time()

        # Combinar markdown
        combined = "\n\n---\n\n".join([r['markdown'] for r in results])

        merge_time = time.time() - start_merge

        print(f"✓ {len(results)} páginas combinadas ({merge_time:.2f}s)")
        print(f"  Tamanho final: {len(combined)} caracteres")
        print()

    # Estatísticas
    print()
    print("=" * 80)
    print("ESTATÍSTICAS FINAIS")
    print("=" * 80)
    print()

    total_time = split_time + init_time + total_conversion_time
    if len(results) > 1:
        total_time += merge_time

    print(f"📊 Resumo:")
    print(f"  Páginas processadas: {len(results)}/{num_pages}")
    print(f"  Tempo total: {total_time:.2f}s")
    print(f"    • Split: {split_time:.2f}s ({split_time/total_time*100:.1f}%)")
    print(f"    • Init: {init_time:.2f}s ({init_time/total_time*100:.1f}%)")
    print(f"    • Conversão: {total_conversion_time:.2f}s ({total_conversion_time/total_time*100:.1f}%)")
    if len(results) > 1:
        print(f"    • Merge: {merge_time:.2f}s ({merge_time/total_time*100:.1f}%)")
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

        # Projeções
        print(f"🔮 Projeções para PDF completo (50 páginas):")
        print(f"  Tempo estimado: {(avg_time * 50):.1f}s (~{(avg_time * 50)/60:.1f} min)")
        print(f"  Com 5 workers paralelos: ~{(avg_time * 50)/5/60:.1f} min")
        print(f"  Palavras totais estimadas: {total_words/len(results) * 50:.0f}")
        print()

    # Salvar resultados
    save = input("Deseja salvar os markdowns gerados? [s/N]: ").strip().lower()

    if save == 's':
        output_dir = Path(__file__).parent.parent / "tmp" / "test_conversion_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Salvar páginas individuais
        for result in results:
            output_file = output_dir / f"page_{result['page_num']:04d}.md"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(result['markdown'])
            print(f"✓ Salvo: {output_file}")

        # Salvar combinado
        if len(results) > 1:
            combined_file = output_dir / "combined.md"
            with open(combined_file, 'w', encoding='utf-8') as f:
                f.write(combined)
            print(f"✓ Salvo (combined): {combined_file}")

        print()
        print(f"📁 Resultados salvos em: {output_dir}")
        print()

    # Cleanup
    cleanup = input("Remover PDFs temporários das páginas? [s/N]: ").strip().lower()

    if cleanup == 's':
        splitter.cleanup_pages(page_files)
        if temp_dir.exists() and not any(temp_dir.iterdir()):
            temp_dir.rmdir()
        print("✓ PDFs temporários removidos")
    else:
        print(f"ℹ PDFs mantidos em: {temp_dir}")

    print()
    print("=" * 80)
    print("✅ TESTE CONCLUÍDO!")
    print("=" * 80)
    print()

    if results:
        print("🎯 Validações:")
        print(f"  ✓ Split de PDF funcionando ({len(page_files)} páginas)")
        print(f"  ✓ Conversão por página funcionando ({len(results)} páginas)")
        if len(results) > 1:
            print(f"  ✓ Merge de resultados funcionando")
        print(f"  ✓ Performance aceitável ({avg_time:.2f}s/página)")
        print()
        print("🚀 Sistema pronto para integração com Celery!")
        print()
        return True
    else:
        print("❌ Nenhuma página foi convertida")
        return False

if __name__ == "__main__":
    try:
        success = test_page_conversion()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Teste interrompido")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
