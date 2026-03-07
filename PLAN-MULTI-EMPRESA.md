# Plan: Multi-Empresa Smartsheet-Bind Middleware

## Estado: EN PROGRESO

## Fases

- [x] Fase 1: Modelo de datos (Company + migración ProcessConfig)
- [x] Fase 2: Services dinámicos (BindClient/catalogs por empresa)
- [ ] Fase 3: Scheduler dinámico (jobs por empresa)
- [ ] Fase 4: API Admin + Dashboard multi-empresa
- [ ] Fase 5: Migración datos AWALab existentes

## Convenciones
- company.id = slug: "awalab", "empresa2"
- job_id formato: "{company_id}__{job_type}" ej: "awalab__sync_invoices"
- Mismo SMARTSHEET_ACCESS_TOKEN para todas las empresas
- Diferente BIND_API_KEY por empresa (en tabla companies)
