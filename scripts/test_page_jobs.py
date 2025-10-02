#!/usr/bin/env python3
"""
Teste CLI simulando jobs de conversão de páginas
Simula o fluxo completo: MAIN → SPLIT → PAGES → MERGE
"""

import sys
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Adicionar pasta shared ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.pdf_splitter import PDFSplitter

# Cores
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Simular estrutura de jobs
class JobSimulator:
    def __init__(self):
        self.jobs = {}  # job_id -> job_data

    def create_job(self, job_type: str, parent_job_id: str = None, page_number: int = None):
        """Cria um novo job"""
        job_id = str(uuid.uuid4())[:8]  # ID curto para facilitar visualização

        job_data = {
            'job_id': job_id,
            'type': job_type,
            'status': 'queued',
            'progress': 0,
            'created_at': datetime.now(),
            'parent_job_id': parent_job_id,
            'page_number': page_number,
            'child_job_ids': [],
        }

        self.jobs[job_id] = job_data

        # Adicionar como child do parent
        if parent_job_id and parent_job_id in self.jobs:
            self.jobs[parent_job_id]['child_job_ids'].append(job_id)

        return job_id

    def update_job(self, job_id: str, status: str = None, progress: int = None):
        """Atualiza status de um job"""
        if job_id in self.jobs:
            if status:
                self.jobs[job_id]['status'] = status
            if progress is not None:
                self.jobs[job_id]['progress'] = progress
            if status == 'completed':
                self.jobs[job_id]['completed_at'] = datetime.now()

    def get_job(self, job_id: str):
        """Retorna dados de um job"""
        return self.jobs.get(job_id)

    def get_page_jobs(self, main_job_id: str):
        """Retorna todos os page jobs de um main job"""
        page_jobs = []
        for job_id, job_data in self.jobs.items():
            if job_data['type'] == 'page' and job_data['parent_job_id'] == main_job_id:
                page_jobs.append(job_data)
        return sorted(page_jobs, key=lambda x: x['page_number'])

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}\n")

def print_job(job_data):
    """Imprime informações de um job"""
    job_type = job_data['type'].upper()
    status = job_data['status']

    # Cor baseada no status
    if status == 'completed':
        status_color = Colors.OKGREEN
    elif status == 'processing':
        status_color = Colors.OKCYAN
    elif status == 'failed':
        status_color = Colors.FAIL
    else:
        status_color = Colors.WARNING

    print(f"  [{job_type:6s}] {job_data['job_id']} ", end='')
    print(f"{status_color}{status:12s}{Colors.ENDC} ", end='')
    print(f"({job_data['progress']:3d}%) ", end='')

    if job_data['page_number']:
        print(f"| Page {job_data['page_number']:2d}", end='')

    if job_data['parent_job_id']:
        print(f" | Parent: {job_data['parent_job_id']}", end='')

    print()

def simulate_conversion():
    """Simula fluxo completo de conversão"""

    # Setup
    pdf_path = Path(__file__).parent.parent / "AI-50p.pdf"
    temp_dir = Path(__file__).parent.parent / "tmp" / "test_jobs"

    if not pdf_path.exists():
        print(f"{Colors.FAIL}❌ PDF não encontrado: {pdf_path}{Colors.ENDC}")
        return

    print(f"{Colors.OKGREEN}✓ PDF encontrado: {pdf_path.name}{Colors.ENDC}")
    print(f"  Tamanho: {pdf_path.stat().st_size / 1024:.2f} KB\n")

    # Criar simulador de jobs
    simulator = JobSimulator()

    # ========================================
    # ETAPA 1: MAIN JOB (Upload)
    # ========================================
    print_header("ETAPA 1: MAIN JOB - Upload e Criação do Job Principal")

    main_job_id = simulator.create_job('main')
    print(f"{Colors.OKGREEN}✓ MAIN JOB criado: {main_job_id}{Colors.ENDC}")
    print_job(simulator.get_job(main_job_id))

    input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

    # Download simulado
    simulator.update_job(main_job_id, status='processing', progress=10)
    print(f"\n{Colors.OKCYAN}⟳ Download do arquivo... (10%){Colors.ENDC}")
    time.sleep(0.5)

    # ========================================
    # ETAPA 2: SPLIT JOB (Divisão do PDF)
    # ========================================
    print_header("ETAPA 2: SPLIT JOB - Divisão do PDF em Páginas")

    split_job_id = simulator.create_job('split', parent_job_id=main_job_id)
    simulator.update_job(split_job_id, status='processing', progress=0)

    print(f"{Colors.OKGREEN}✓ SPLIT JOB criado: {split_job_id}{Colors.ENDC}")
    print(f"  Parent: {main_job_id}\n")

    print(f"{Colors.OKCYAN}⟳ Dividindo PDF em páginas...{Colors.ENDC}")

    # Dividir PDF de verdade
    splitter = PDFSplitter(temp_dir=temp_dir)
    page_files = splitter.split_pdf(pdf_path)
    total_pages = len(page_files)

    simulator.update_job(split_job_id, status='completed', progress=100)
    simulator.update_job(main_job_id, progress=20)

    print(f"{Colors.OKGREEN}✓ PDF dividido em {total_pages} páginas{Colors.ENDC}")
    print_job(simulator.get_job(split_job_id))

    input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

    # ========================================
    # ETAPA 3: PAGE JOBS (Conversão das Páginas)
    # ========================================
    print_header(f"ETAPA 3: PAGE JOBS - Conversão de {total_pages} Páginas em Paralelo")

    print(f"{Colors.OKCYAN}⟳ Criando {total_pages} page jobs...{Colors.ENDC}\n")

    # Criar page jobs
    page_job_ids = []
    for page_num, page_path in page_files:
        page_job_id = simulator.create_job(
            'page',
            parent_job_id=main_job_id,
            page_number=page_num
        )
        page_job_ids.append(page_job_id)

    print(f"{Colors.OKGREEN}✓ {len(page_job_ids)} page jobs criados{Colors.ENDC}")

    # Mostrar primeiros 10 jobs
    print(f"\n{Colors.BOLD}Primeiros 10 page jobs:{Colors.ENDC}")
    for i in range(min(10, len(page_job_ids))):
        job_id = page_job_ids[i]
        print_job(simulator.get_job(job_id))

    if len(page_job_ids) > 10:
        print(f"  ... (+ {len(page_job_ids) - 10} page jobs)")

    input(f"\n{Colors.BOLD}Pressione Enter para simular conversão...{Colors.ENDC}")

    # Simular conversão das páginas (processamento paralelo)
    print(f"\n{Colors.OKCYAN}⟳ Processando páginas em paralelo...{Colors.ENDC}\n")

    # Simular processamento em lotes (como seria com workers paralelos)
    batch_size = 5  # Simula 5 workers paralelos
    completed = 0

    for i in range(0, len(page_job_ids), batch_size):
        batch = page_job_ids[i:i+batch_size]

        # Marcar batch como processing
        for job_id in batch:
            simulator.update_job(job_id, status='processing', progress=0)

        # Simular processamento
        print(f"  Batch {i//batch_size + 1}: Processando páginas {i+1}-{min(i+batch_size, len(page_job_ids))}... ", end='', flush=True)
        time.sleep(0.3)  # Simular tempo de conversão

        # Marcar batch como completed
        for job_id in batch:
            simulator.update_job(job_id, status='completed', progress=100)
            completed += 1

        # Atualizar progresso do main job
        # Páginas representam 70% do progresso (20% a 90%)
        pages_progress = int((completed / total_pages) * 70)
        main_progress = 20 + pages_progress
        simulator.update_job(main_job_id, progress=main_progress)

        print(f"{Colors.OKGREEN}✓{Colors.ENDC} ({completed}/{total_pages} páginas - {main_progress}%)")

    print(f"\n{Colors.OKGREEN}✓ Todas as {total_pages} páginas convertidas!{Colors.ENDC}")

    # Mostrar status de alguns page jobs
    print(f"\n{Colors.BOLD}Status de alguns page jobs:{Colors.ENDC}")
    sample_indices = [0, 1, 2, total_pages//2, total_pages-2, total_pages-1]
    for idx in sample_indices:
        if idx < len(page_job_ids):
            print_job(simulator.get_job(page_job_ids[idx]))

    input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

    # ========================================
    # ETAPA 4: MERGE JOB (Combinação dos Resultados)
    # ========================================
    print_header("ETAPA 4: MERGE JOB - Combinação dos Resultados")

    merge_job_id = simulator.create_job('merge', parent_job_id=main_job_id)
    simulator.update_job(merge_job_id, status='processing', progress=0)

    print(f"{Colors.OKGREEN}✓ MERGE JOB criado: {merge_job_id}{Colors.ENDC}")
    print(f"  Parent: {main_job_id}\n")

    print(f"{Colors.OKCYAN}⟳ Combinando resultados de {total_pages} páginas...{Colors.ENDC}")
    time.sleep(0.5)

    # Simular merge
    simulator.update_job(merge_job_id, status='completed', progress=100)
    simulator.update_job(main_job_id, status='completed', progress=100)

    print(f"{Colors.OKGREEN}✓ Resultados combinados com sucesso!{Colors.ENDC}")
    print_job(simulator.get_job(merge_job_id))

    input(f"\n{Colors.BOLD}Pressione Enter para ver resumo final...{Colors.ENDC}")

    # ========================================
    # RESUMO FINAL
    # ========================================
    print_header("RESUMO FINAL - Hierarquia Completa de Jobs")

    main_job = simulator.get_job(main_job_id)
    split_job = simulator.get_job(split_job_id)
    merge_job = simulator.get_job(merge_job_id)
    page_jobs = simulator.get_page_jobs(main_job_id)

    print(f"{Colors.BOLD}MAIN JOB:{Colors.ENDC}")
    print_job(main_job)

    print(f"\n{Colors.BOLD}  ├─ SPLIT JOB:{Colors.ENDC}")
    print(f"  │  ", end='')
    print_job(split_job)

    print(f"\n{Colors.BOLD}  ├─ PAGE JOBS ({len(page_jobs)} total):{Colors.ENDC}")
    for i in range(min(5, len(page_jobs))):
        print(f"  │  ", end='')
        print_job(page_jobs[i])

    if len(page_jobs) > 5:
        print(f"  │  ... ({len(page_jobs) - 5} more pages)")

    print(f"\n{Colors.BOLD}  └─ MERGE JOB:{Colors.ENDC}")
    print(f"     ", end='')
    print_job(merge_job)

    # Estatísticas
    print(f"\n{Colors.BOLD}📊 Estatísticas:{Colors.ENDC}")
    print(f"  Total de jobs criados: {len(simulator.jobs)}")
    print(f"  • 1 MAIN job")
    print(f"  • 1 SPLIT job")
    print(f"  • {len(page_jobs)} PAGE jobs")
    print(f"  • 1 MERGE job")

    completed_jobs = sum(1 for j in simulator.jobs.values() if j['status'] == 'completed')
    print(f"\n  Jobs completados: {completed_jobs}/{len(simulator.jobs)}")

    # Tempo total (simulado)
    if main_job.get('completed_at'):
        duration = (main_job['completed_at'] - main_job['created_at']).total_seconds()
        print(f"  Tempo total: {duration:.2f}s (simulado)")

    # Cleanup
    print(f"\n{Colors.BOLD}🧹 Limpeza:{Colors.ENDC}")
    cleanup = input("  Remover arquivos temporários? (s/N): ").strip().lower()
    if cleanup == 's':
        splitter.cleanup_pages(page_files)
        if temp_dir.exists() and not any(temp_dir.iterdir()):
            temp_dir.rmdir()
        print(f"  {Colors.OKGREEN}✓ Arquivos temporários removidos{Colors.ENDC}")
    else:
        print(f"  {Colors.WARNING}ℹ Arquivos mantidos em: {temp_dir}{Colors.ENDC}")

    # Visualização ASCII da hierarquia
    print(f"\n{Colors.BOLD}🌳 Hierarquia Visual:{Colors.ENDC}")
    print(f"""
    {Colors.OKCYAN}MAIN{Colors.ENDC} ({main_job_id})
     │
     ├── {Colors.OKBLUE}SPLIT{Colors.ENDC} ({split_job_id})
     │    └── Divide PDF em {total_pages} páginas
     │
     ├── {Colors.OKGREEN}PAGE JOBS{Colors.ENDC} ({len(page_jobs)} jobs em paralelo)
     │    ├── Page 1  ({page_jobs[0]['job_id']})
     │    ├── Page 2  ({page_jobs[1]['job_id']})
     │    ├── ...
     │    └── Page {total_pages} ({page_jobs[-1]['job_id']})
     │
     └── {Colors.WARNING}MERGE{Colors.ENDC} ({merge_job_id})
          └── Combina {total_pages} resultados
    """)

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}✓ Simulação completa!{Colors.ENDC}")
    print(f"\n{Colors.BOLD}🎯 Este é exatamente o fluxo que acontecerá no sistema real:{Colors.ENDC}")
    print(f"  1. API recebe upload (MAIN JOB)")
    print(f"  2. Worker divide PDF (SPLIT JOB)")
    print(f"  3. Workers convertem páginas em paralelo (PAGE JOBS)")
    print(f"  4. Worker combina resultados (MERGE JOB)")
    print(f"  5. Usuário pode consultar qualquer job individualmente!")

if __name__ == "__main__":
    try:
        simulate_conversion()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Simulação interrompida pelo usuário{Colors.ENDC}")
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Erro: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
