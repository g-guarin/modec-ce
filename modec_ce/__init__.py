"""
MODEC-CE — Costo y Evidencia para orquestación multiagente sobre LLM.

Extiende la metodología MODEC (Orquestación por Dinámica de Estados Comprimidos)
con tres capacidades demostrables:

  1. Disposición de prompts consciente del caché de prefijos del proveedor
     (DeepSeek Context Caching on Disk): mismo contenido, distinto orden.
  2. Historial comprimido en Super-Tokens con referencia direccionada por
     contenido (SHA-256), con medición mecánica de preservación de anclas.
  3. Evidencia sellada (núcleo PESD P1/P2) de cada medición: uso informado por el
     proveedor, costo derivado y procedencia, verificable por un tercero.

Sin datos ni calibración externos: las cargas de trabajo son sintéticas y la
medición real proviene de los campos `usage` del propio proveedor.
"""
__version__ = "0.3.0"
