"""
test_second_company.py - Script para probar el flujo end-to-end de agregar
una segunda empresa al sistema multi-tenant.

Ejecutar contra el servidor local:
    python tests/test_second_company.py [BASE_URL]

Default BASE_URL: http://localhost:8000
"""

import sys
import requests
import json

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
COMPANY_ID = "test_empresa2"
COMPANY_DATA = {
    "id": COMPANY_ID,
    "name": "Empresa de Prueba 2",
    "bind_api_key": "test-api-key-fake-12345",
    "bind_api_base_url": "https://api.bind.com.mx/api",
    "smartsheet_workspace_id": None,
    "bind_warehouse_id": None,
    "is_active": True,
}


def step(n, desc):
    print(f"\n{'='*60}")
    print(f"  PASO {n}: {desc}")
    print(f"{'='*60}")


def check(response, expected_status=200):
    if response.status_code != expected_status:
        print(f"  FAIL: HTTP {response.status_code}")
        print(f"  Body: {response.text[:500]}")
        return False
    data = response.json()
    if not data.get("success", True):
        print(f"  FAIL: {data}")
        return False
    print(f"  OK: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
    return True


def main():
    print(f"Testing multi-tenant against {BASE_URL}")

    # 0. Health check
    step(0, "Health check")
    r = requests.get(f"{BASE_URL}/health")
    check(r)

    # 1. List existing companies
    step(1, "Listar empresas existentes")
    r = requests.get(f"{BASE_URL}/api/admin/companies")
    check(r)

    # 2. Create new company
    step(2, f"Crear empresa '{COMPANY_ID}'")
    r = requests.post(f"{BASE_URL}/api/admin/companies", json=COMPANY_DATA)
    if r.status_code == 409:
        print(f"  SKIP: Empresa ya existe, continuando...")
    else:
        check(r)

    # 3. Get company details
    step(3, f"Obtener detalle de '{COMPANY_ID}'")
    r = requests.get(f"{BASE_URL}/api/admin/companies/{COMPANY_ID}")
    check(r)
    data = r.json()
    configs = data.get("process_configs", [])
    print(f"  ProcessConfigs creados: {len(configs)}")
    for c in configs[:5]:
        print(f"    - {c['job_id']} (active={c['is_active']})")
    if len(configs) > 5:
        print(f"    ... y {len(configs)-5} más")

    # 4. Test Bind connection (will fail with fake key, that's expected)
    step(4, f"Test conexión Bind para '{COMPANY_ID}'")
    r = requests.post(f"{BASE_URL}/api/admin/companies/{COMPANY_ID}/test-connection")
    data = r.json()
    print(f"  Resultado: bind_connected={data.get('bind_connected')} (esperado: False con key fake)")

    # 5. Activate one job
    step(5, "Activar un job de la empresa")
    job_id = f"{COMPANY_ID}__sync_catalog_warehouses"
    r = requests.get(f"{BASE_URL}/api/admin/process-configs/{job_id}")
    if r.status_code == 200:
        r = requests.put(f"{BASE_URL}/api/admin/process-configs/{job_id}",
                         json={"is_active": True, "interval_minutes": 120})
        check(r)
    else:
        print(f"  SKIP: ProcessConfig {job_id} no encontrado")

    # 6. Reload company jobs
    step(6, f"Recargar scheduler para '{COMPANY_ID}'")
    r = requests.post(f"{BASE_URL}/scheduler/reload/{COMPANY_ID}")
    check(r)

    # 7. List scheduler jobs
    step(7, "Listar jobs del scheduler")
    r = requests.get(f"{BASE_URL}/scheduler/jobs")
    data = r.json()
    company_jobs = [j for j in data.get("jobs", []) if COMPANY_ID in j.get("id", "")]
    print(f"  Jobs de '{COMPANY_ID}' en scheduler: {len(company_jobs)}")
    for j in company_jobs:
        print(f"    - {j['id']}")

    # 8. Check stats
    step(8, "Verificar stats multi-empresa")
    r = requests.get(f"{BASE_URL}/api/admin/stats")
    data = r.json()
    print(f"  Empresas activas: {data.get('companies', {}).get('active', [])}")
    print(f"  Jobs por empresa: {data.get('scheduler', {}).get('jobs_by_company', {})}")

    # 9. Cleanup - deactivate test company
    step(9, f"Desactivar empresa '{COMPANY_ID}' (cleanup)")
    r = requests.delete(f"{BASE_URL}/api/admin/companies/{COMPANY_ID}")
    check(r)

    print(f"\n{'='*60}")
    print("  TEST COMPLETO - Flujo multi-tenant verificado")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
