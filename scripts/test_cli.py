#!/usr/bin/env python3
"""
Script interativo para testar a API Doc2MD
Usa o PDF AI-50p.pdf da raiz do projeto
"""

import requests
import json
import time
import os
from pathlib import Path
from typing import Optional

# Configurações
API_BASE_URL = "http://localhost:8080"
PDF_PATH = Path(__file__).parent.parent / "AI-50p.pdf"

# Cores para output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}\n")

def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

def print_json(data):
    print(f"{Colors.OKBLUE}{json.dumps(data, indent=2, ensure_ascii=False)}{Colors.ENDC}")

def check_api_health():
    """Verifica se a API está rodando"""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success("API está rodando!")
            print_json(data)
            return True
        else:
            print_error(f"API retornou status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Não foi possível conectar à API. Certifique-se que ela está rodando.")
        print_info("Execute: docker compose up -d")
        return False
    except Exception as e:
        print_error(f"Erro ao verificar API: {e}")
        return False

def upload_pdf():
    """Faz upload do PDF e retorna job_id"""
    if not PDF_PATH.exists():
        print_error(f"PDF não encontrado: {PDF_PATH}")
        return None

    print_info(f"Fazendo upload de: {PDF_PATH.name}")

    try:
        with open(PDF_PATH, 'rb') as f:
            files = {'file': (PDF_PATH.name, f, 'application/pdf')}
            data = {'source_type': 'file'}

            response = requests.post(
                f"{API_BASE_URL}/convert",
                files=files,
                data=data,
                timeout=30
            )

        if response.status_code == 200:
            result = response.json()
            job_id = result.get('job_id')
            print_success(f"Upload realizado! Job ID: {job_id}")
            print_json(result)
            return job_id
        else:
            print_error(f"Erro no upload: {response.status_code}")
            print(response.text)
            return None

    except Exception as e:
        print_error(f"Erro ao fazer upload: {e}")
        return None

def get_job_status(job_id: str):
    """Consulta status de um job"""
    try:
        response = requests.get(f"{API_BASE_URL}/jobs/{job_id}", timeout=10)

        if response.status_code == 200:
            data = response.json()

            job_type = data.get('type', 'unknown')
            status = data.get('status', 'unknown')
            progress = data.get('progress', 0)

            print_success(f"Status do Job {job_id}:")
            print(f"  Type: {Colors.BOLD}{job_type}{Colors.ENDC}")
            print(f"  Status: {Colors.BOLD}{status}{Colors.ENDC}")
            print(f"  Progress: {Colors.BOLD}{progress}%{Colors.ENDC}")

            if data.get('total_pages'):
                print(f"  Total Pages: {data['total_pages']}")
                print(f"  Pages Completed: {data.get('pages_completed', 0)}")
                print(f"  Pages Failed: {data.get('pages_failed', 0)}")

            if data.get('child_jobs'):
                print(f"\n  Child Jobs:")
                child_jobs = data['child_jobs']
                if child_jobs.get('split_job_id'):
                    print(f"    Split Job: {child_jobs['split_job_id']}")
                if child_jobs.get('page_job_ids'):
                    print(f"    Page Jobs: {len(child_jobs['page_job_ids'])} jobs")
                if child_jobs.get('merge_job_id'):
                    print(f"    Merge Job: {child_jobs['merge_job_id']}")

            if data.get('page_number'):
                print(f"  Page Number: {data['page_number']}")

            if data.get('parent_job_id'):
                print(f"  Parent Job: {data['parent_job_id']}")

            if data.get('error'):
                print_error(f"  Error: {data['error']}")

            print(f"\n{Colors.OKBLUE}Full Response:{Colors.ENDC}")
            print_json(data)

            return data
        else:
            print_error(f"Erro ao consultar status: {response.status_code}")
            print(response.text)
            return None

    except Exception as e:
        print_error(f"Erro ao consultar status: {e}")
        return None

def get_job_pages(job_id: str):
    """Lista todas as páginas de um job"""
    try:
        response = requests.get(f"{API_BASE_URL}/jobs/{job_id}/pages", timeout=10)

        if response.status_code == 200:
            data = response.json()

            print_success(f"Páginas do Job {job_id}:")
            print(f"  Total Pages: {data['total_pages']}")
            print(f"  Pages Completed: {data['pages_completed']}")
            print(f"  Pages Failed: {data['pages_failed']}")
            print(f"\n  Page Jobs:")

            for page in data['pages']:
                status_color = Colors.OKGREEN if page['status'] == 'completed' else Colors.WARNING
                print(f"    Page {page['page_number']:2d}: {status_color}{page['status']:<12}{Colors.ENDC} | Job: {page['job_id']} | URL: {page['url']}")

            print(f"\n{Colors.OKBLUE}Full Response:{Colors.ENDC}")
            print_json(data)

            return data
        elif response.status_code == 404:
            print_warning("Este job não tem páginas (não é PDF multi-página)")
            return None
        else:
            print_error(f"Erro ao listar páginas: {response.status_code}")
            print(response.text)
            return None

    except Exception as e:
        print_error(f"Erro ao listar páginas: {e}")
        return None

def get_job_result(job_id: str, save_to_file: bool = False):
    """Obtém resultado de um job"""
    try:
        response = requests.get(f"{API_BASE_URL}/jobs/{job_id}/result", timeout=10)

        if response.status_code == 200:
            data = response.json()

            job_type = data.get('type', 'unknown')
            result = data.get('result', {})
            markdown = result.get('markdown', '')
            metadata = result.get('metadata', {})

            print_success(f"Resultado do Job {job_id}:")
            print(f"  Type: {Colors.BOLD}{job_type}{Colors.ENDC}")

            if data.get('page_number'):
                print(f"  Page Number: {data['page_number']}")

            print(f"\n  Metadata:")
            for key, value in metadata.items():
                print(f"    {key}: {value}")

            print(f"\n  Markdown Preview (primeiros 500 chars):")
            print(f"{Colors.OKCYAN}{markdown[:500]}...{Colors.ENDC}")
            print(f"\n  Total Characters: {len(markdown)}")

            if save_to_file:
                output_file = f"result_{job_id}.md"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                print_success(f"Resultado salvo em: {output_file}")

            return data
        elif response.status_code == 400:
            print_warning("Job ainda está em processamento")
            return None
        elif response.status_code == 404:
            print_error("Resultado não encontrado ou expirado")
            return None
        else:
            print_error(f"Erro ao obter resultado: {response.status_code}")
            print(response.text)
            return None

    except Exception as e:
        print_error(f"Erro ao obter resultado: {e}")
        return None

def monitor_job(job_id: str, interval: int = 2):
    """Monitora job até completar"""
    print_info(f"Monitorando job {job_id} (atualizando a cada {interval}s)")
    print_info("Pressione Ctrl+C para parar\n")

    try:
        while True:
            status_data = get_job_status(job_id)

            if not status_data:
                print_error("Não foi possível obter status")
                break

            status = status_data.get('status')

            if status == 'completed':
                print_success("\n✓ Job completado!")
                break
            elif status == 'failed':
                print_error("\n✗ Job falhou!")
                break

            time.sleep(interval)
            print(f"\n{Colors.OKCYAN}--- Atualizando... ---{Colors.ENDC}\n")

    except KeyboardInterrupt:
        print_warning("\n\nMonitoramento interrompido pelo usuário")

def show_menu():
    """Mostra menu principal"""
    print_header("DOC2MD - Test CLI")
    print("Escolha uma opção:\n")
    print("  1. Health Check - Verificar se API está rodando")
    print("  2. Upload PDF - Fazer upload do AI-50p.pdf")
    print("  3. Status do Job - Consultar status de um job")
    print("  4. Listar Páginas - Ver todas as páginas de um job")
    print("  5. Resultado do Job - Obter resultado (main ou page)")
    print("  6. Monitorar Job - Acompanhar progresso em tempo real")
    print("  7. Fluxo Completo - Upload + Monitor + Resultado")
    print("  0. Sair\n")

def main():
    """Loop principal"""
    last_job_id = None

    while True:
        show_menu()

        if last_job_id:
            print_info(f"Último Job ID: {last_job_id}\n")

        try:
            choice = input(f"{Colors.BOLD}Digite sua escolha: {Colors.ENDC}").strip()
        except KeyboardInterrupt:
            print("\n")
            break

        if choice == '0':
            print_success("Até logo!")
            break

        elif choice == '1':
            print_header("Health Check")
            check_api_health()

        elif choice == '2':
            print_header("Upload PDF")
            job_id = upload_pdf()
            if job_id:
                last_job_id = job_id

        elif choice == '3':
            print_header("Status do Job")
            job_id = input("Job ID (Enter para usar o último): ").strip()
            if not job_id:
                job_id = last_job_id
            if job_id:
                get_job_status(job_id)
            else:
                print_warning("Nenhum job ID fornecido")

        elif choice == '4':
            print_header("Listar Páginas")
            job_id = input("Job ID (Enter para usar o último): ").strip()
            if not job_id:
                job_id = last_job_id
            if job_id:
                get_job_pages(job_id)
            else:
                print_warning("Nenhum job ID fornecido")

        elif choice == '5':
            print_header("Resultado do Job")
            job_id = input("Job ID (Enter para usar o último): ").strip()
            if not job_id:
                job_id = last_job_id
            if job_id:
                save = input("Salvar em arquivo? (s/N): ").strip().lower() == 's'
                get_job_result(job_id, save_to_file=save)
            else:
                print_warning("Nenhum job ID fornecido")

        elif choice == '6':
            print_header("Monitorar Job")
            job_id = input("Job ID (Enter para usar o último): ").strip()
            if not job_id:
                job_id = last_job_id
            if job_id:
                interval = input("Intervalo em segundos (default 2): ").strip()
                interval = int(interval) if interval else 2
                monitor_job(job_id, interval)
            else:
                print_warning("Nenhum job ID fornecido")

        elif choice == '7':
            print_header("Fluxo Completo")

            # 1. Health check
            print_info("Passo 1/4: Health Check")
            if not check_api_health():
                print_error("API não está disponível. Abortando.")
                continue

            input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

            # 2. Upload
            print_header("Passo 2/4: Upload PDF")
            job_id = upload_pdf()
            if not job_id:
                print_error("Falha no upload. Abortando.")
                continue

            last_job_id = job_id
            input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

            # 3. Monitor
            print_header("Passo 3/4: Monitorar Progresso")
            monitor_job(job_id, interval=3)

            input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

            # 4. Resultado
            print_header("Passo 4/4: Obter Resultado")

            # Listar páginas primeiro
            print_info("4a. Listando páginas...")
            pages_data = get_job_pages(job_id)

            input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

            # Pegar resultado de uma página individual
            if pages_data and pages_data.get('pages'):
                print_info("4b. Obtendo resultado da página 1...")
                first_page = pages_data['pages'][0]
                get_job_result(first_page['job_id'])

                input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

            # Pegar resultado completo merged
            print_info("4c. Obtendo resultado completo (merged)...")
            save = input("Salvar resultado completo em arquivo? (s/N): ").strip().lower() == 's'
            get_job_result(job_id, save_to_file=save)

            print_success("\n✓ Fluxo completo finalizado!")

        else:
            print_warning("Opção inválida")

        input(f"\n{Colors.BOLD}Pressione Enter para continuar...{Colors.ENDC}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Programa interrompido pelo usuário{Colors.ENDC}")
    except Exception as e:
        print_error(f"Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
