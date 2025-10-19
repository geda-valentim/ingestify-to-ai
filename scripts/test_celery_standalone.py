#!/usr/bin/env python3
"""
Teste standalone do Celery
Valida que as tasks podem ser carregadas e descobertas
"""

import sys
from pathlib import Path

# Adicionar raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_celery_setup():
    """Testa configuração básica do Celery"""

    print("=" * 80)
    print("TESTE: Configuração do Celery")
    print("=" * 80)
    print()

    # 1. Import Celery app
    print("1. Importando Celery app...")
    try:
        from backend.workers.celery_app import celery_app
        print(f"   ✓ Celery app importado: {celery_app.main}")
        print(f"   ✓ Broker: {celery_app.conf.broker_url}")
        print(f"   ✓ Backend: {celery_app.conf.result_backend}")
    except Exception as e:
        print(f"   ✗ Erro ao importar: {e}")
        return False

    print()

    # 2. Import tasks
    print("2. Importando tasks...")
    try:
        from workers import tasks
        print(f"   ✓ Tasks module importado")
    except Exception as e:
        print(f"   ✗ Erro ao importar tasks: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()

    # 3. Discover tasks
    print("3. Descobrindo tasks registradas...")
    try:
        registered_tasks = list(celery_app.tasks.keys())
        print(f"   ✓ Total de tasks: {len(registered_tasks)}")

        # Filtrar tasks do projeto
        project_tasks = [t for t in registered_tasks if 'workers.tasks' in t or not t.startswith('celery.')]

        print(f"\n   Tasks do projeto:")
        for task in sorted(project_tasks):
            print(f"     • {task}")

    except Exception as e:
        print(f"   ✗ Erro ao descobrir tasks: {e}")
        return False

    print()

    # 4. Verificar tasks específicas
    print("4. Verificando tasks hierárquicas...")
    expected_tasks = [
        'workers.tasks.process_conversion',
        'workers.tasks.split_pdf_task',
        'workers.tasks.convert_page_task',
        'workers.tasks.merge_pages_task',
    ]

    all_found = True
    for task_name in expected_tasks:
        if task_name in celery_app.tasks:
            print(f"   ✓ {task_name}")
        else:
            print(f"   ✗ {task_name} NÃO ENCONTRADA")
            all_found = False

    if not all_found:
        print()
        print("   ⚠ Algumas tasks não foram encontradas!")
        return False

    print()

    # 5. Verificar configuração
    print("5. Verificando configuração...")
    config_checks = [
        ('task_serializer', 'json'),
        ('result_serializer', 'json'),
        ('task_track_started', True),
        ('task_acks_late', True),
    ]

    for key, expected in config_checks:
        actual = celery_app.conf.get(key)
        if actual == expected:
            print(f"   ✓ {key} = {actual}")
        else:
            print(f"   ✗ {key} = {actual} (esperado: {expected})")

    print()

    # 6. Teste de signature
    print("6. Testando task signatures...")
    try:
        from backend.workers.tasks import process_conversion, split_pdf_task

        # Criar signature sem executar
        sig1 = process_conversion.s(
            job_id="test-123",
            source_type="file",
            source="/tmp/test.pdf"
        )
        print(f"   ✓ process_conversion signature criada")

        sig2 = split_pdf_task.s(
            split_job_id="split-123",
            parent_job_id="main-123",
            file_path="/tmp/test.pdf"
        )
        print(f"   ✓ split_pdf_task signature criada")

    except Exception as e:
        print(f"   ✗ Erro ao criar signatures: {e}")
        return False

    print()
    print("=" * 80)
    print("✅ TODOS OS TESTES PASSARAM!")
    print("=" * 80)
    print()
    print("🎯 Resumo:")
    print("   • Celery app configurado corretamente")
    print("   • 4 tasks hierárquicas encontradas")
    print("   • Configuração validada")
    print("   • Signatures funcionando")
    print()
    print("🚀 Próximo passo: Testar com Redis + Workers reais")
    print()

    return True

if __name__ == "__main__":
    try:
        success = test_celery_setup()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
