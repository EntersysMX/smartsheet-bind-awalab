"""
Script para configurar la hoja de Smartsheet con las columnas correctas
y agregar registros de ejemplo para facturacion.
"""

import smartsheet
from smartsheet.models import Column, Row, Cell

# Configuracion
ACCESS_TOKEN = 'rVcpRyiLctXXwjnmh09dEpPiZfzrodlTUdBWd'
SHEET_ID = 4956740131966852

# Columnas requeridas para facturacion
REQUIRED_COLUMNS = [
    {"title": "RFC", "type": "TEXT_NUMBER", "primary": True},
    {"title": "Razon Social", "type": "TEXT_NUMBER"},
    {"title": "Concepto", "type": "TEXT_NUMBER"},
    {"title": "Descripcion", "type": "TEXT_NUMBER"},
    {"title": "Cantidad", "type": "TEXT_NUMBER"},
    {"title": "Precio Unitario", "type": "TEXT_NUMBER"},
    {"title": "Clave SAT Producto", "type": "TEXT_NUMBER"},
    {"title": "Clave SAT Unidad", "type": "TEXT_NUMBER"},
    {"title": "Metodo Pago", "type": "PICKLIST", "options": ["PUE", "PPD"]},
    {"title": "Forma Pago", "type": "TEXT_NUMBER"},
    {"title": "Uso CFDI", "type": "TEXT_NUMBER"},
    {"title": "Regimen Fiscal", "type": "TEXT_NUMBER"},
    {"title": "Codigo Postal", "type": "TEXT_NUMBER"},
    {"title": "Estado", "type": "PICKLIST", "options": ["Pendiente", "Facturar", "Facturado", "Error"]},
    {"title": "UUID", "type": "TEXT_NUMBER"},
    {"title": "Folio Fiscal", "type": "TEXT_NUMBER"},
    {"title": "Fecha Facturacion", "type": "TEXT_NUMBER"},
    {"title": "Resultado", "type": "TEXT_NUMBER"},
]

# Registros de ejemplo
SAMPLE_RECORDS = [
    {
        "RFC": "XAXX010101000",
        "Razon Social": "Publico en General",
        "Concepto": "Servicio de consultoria tecnologica",
        "Descripcion": "Horas de asesoria en sistemas",
        "Cantidad": "10",
        "Precio Unitario": "1500.00",
        "Clave SAT Producto": "81111500",
        "Clave SAT Unidad": "E48",
        "Metodo Pago": "PUE",
        "Forma Pago": "03",
        "Uso CFDI": "G03",
        "Regimen Fiscal": "601",
        "Codigo Postal": "44100",
        "Estado": "Pendiente",
    },
    {
        "RFC": "CACX7605101P8",
        "Razon Social": "Cliente Ejemplo SA de CV",
        "Concepto": "Desarrollo de software a medida",
        "Descripcion": "Sistema de gestion de inventarios",
        "Cantidad": "1",
        "Precio Unitario": "25000.00",
        "Clave SAT Producto": "81112100",
        "Clave SAT Unidad": "E48",
        "Metodo Pago": "PUE",
        "Forma Pago": "03",
        "Uso CFDI": "G03",
        "Regimen Fiscal": "601",
        "Codigo Postal": "06600",
        "Estado": "Pendiente",
    },
    {
        "RFC": "GODE561231GR8",
        "Razon Social": "Empresa Demo",
        "Concepto": "Mantenimiento mensual de servidores",
        "Descripcion": "Soporte tecnico y monitoreo 24/7",
        "Cantidad": "1",
        "Precio Unitario": "8500.00",
        "Clave SAT Producto": "81111501",
        "Clave SAT Unidad": "E48",
        "Metodo Pago": "PUE",
        "Forma Pago": "03",
        "Uso CFDI": "G03",
        "Regimen Fiscal": "612",
        "Codigo Postal": "44600",
        "Estado": "Pendiente",
    },
]


def main():
    client = smartsheet.Smartsheet(ACCESS_TOKEN)
    client.errors_as_exceptions(True)

    print("Obteniendo hoja...")
    sheet = client.Sheets.get_sheet(SHEET_ID)
    print(f"Hoja: {sheet.name}")

    # Mapeo de columnas existentes
    existing_columns = {col.title: col for col in sheet.columns}
    print(f"Columnas existentes: {list(existing_columns.keys())}")

    # Paso 1: Renombrar/actualizar columnas existentes y agregar nuevas
    print("\nConfigurando columnas...")

    columns_to_add = []
    column_map = {}  # title -> column_id

    # Primero, actualizar columnas existentes
    existing_col_list = list(sheet.columns)
    for i, req_col in enumerate(REQUIRED_COLUMNS):
        if i < len(existing_col_list):
            # Actualizar columna existente
            col = existing_col_list[i]
            update_col = Column()
            update_col.title = req_col["title"]
            if "options" in req_col:
                update_col.options = req_col["options"]

            try:
                result = client.Sheets.update_column(SHEET_ID, col.id, update_col)
                print(f"  Actualizada: {req_col['title']}")
                column_map[req_col["title"]] = col.id
            except Exception as e:
                print(f"  Error actualizando {req_col['title']}: {e}")
                column_map[req_col["title"]] = col.id
        else:
            # Agregar columna nueva
            new_col = Column()
            new_col.title = req_col["title"]
            new_col.type = req_col["type"]
            if "options" in req_col:
                new_col.options = req_col["options"]
            columns_to_add.append(new_col)

    # Agregar columnas nuevas
    if columns_to_add:
        print(f"\nAgregando {len(columns_to_add)} columnas nuevas...")
        for col in columns_to_add:
            try:
                result = client.Sheets.add_columns(SHEET_ID, [col])
                new_col_id = result.result[0].id
                column_map[col.title] = new_col_id
                print(f"  Agregada: {col.title}")
            except Exception as e:
                print(f"  Error agregando {col.title}: {e}")

    # Recargar hoja para obtener IDs actualizados
    print("\nRecargando hoja...")
    sheet = client.Sheets.get_sheet(SHEET_ID)
    column_map = {col.title: col.id for col in sheet.columns}
    print(f"Columnas finales: {list(column_map.keys())}")

    # Paso 2: Eliminar filas vacias existentes
    if sheet.rows:
        print(f"\nEliminando {len(sheet.rows)} filas vacias...")
        row_ids = [row.id for row in sheet.rows]
        try:
            client.Sheets.delete_rows(SHEET_ID, row_ids)
            print("  Filas eliminadas")
        except Exception as e:
            print(f"  Error eliminando filas: {e}")

    # Paso 3: Agregar registros de ejemplo
    print(f"\nAgregando {len(SAMPLE_RECORDS)} registros de ejemplo...")

    rows_to_add = []
    for record in SAMPLE_RECORDS:
        row = Row()
        row.to_bottom = True
        row.cells = []

        for field, value in record.items():
            if field in column_map:
                cell = Cell()
                cell.column_id = column_map[field]
                cell.value = value
                row.cells.append(cell)

        rows_to_add.append(row)

    try:
        result = client.Sheets.add_rows(SHEET_ID, rows_to_add)
        print(f"  Agregados {len(result.result)} registros")
    except Exception as e:
        print(f"  Error agregando registros: {e}")

    print("\n=== CONFIGURACION COMPLETADA ===")
    print(f"Hoja: {sheet.name}")
    print(f"ID: {SHEET_ID}")
    print(f"URL: https://app.smartsheet.com/sheets/{SHEET_ID}")


if __name__ == "__main__":
    main()
