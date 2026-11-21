# Cómo contribuir

## Reglas que no se negocian

1. **Mismo contenido entre disposiciones.** Una disposición nueva debe producir la misma `Peticion.huella_contenido` que las líneas base. Si cambia el contenido (como la compresión), se declara y se mide aparte.
2. **Ausente no es cero (P2).** Un campo de uso que el proveedor no informa se clasifica AUSENTE o VACIO y la medición queda NO_EVALUABLE. Nunca se rellena con 0. Excepción documentada: en OpenAI y OpenRouter, si la respuesta no trae `cache_write_tokens`, se toma como 0; ese campo no entra en la clasificación de presencia.
3. **Dinero en `Decimal`.** Tarifas, cotas y costos se calculan con `decimal.Decimal`, nunca con `float`, salvo el costo que informa OpenRouter, que llega como número JSON y se convierte al leerlo.
4. **Nada sensible en disco.** No se escriben claves, prompts ni respuestas en resultados ni en la bitácora; solo huellas SHA-256, conteos, latencias, costos y, si hay un fallo, el mensaje de error del proveedor (hasta 300 caracteres).
5. **Procedencia declarada.** Toda cifra nueva dice si es ESTIMADA, MEDIDA, DERIVADA o DECLARADA.
6. **Tarifas con fuente.** Un cambio en `datos/precios.json` cita la página oficial y la fecha de lectura.

## Flujo

1. Cree una rama descriptiva (`feat/…`, `fix/…`, `docs/…`).
2. Añada pruebas sin red en `tests/`.
3. Ejecute `python -B -m unittest discover -s tests`. Si cambian las cifras de la simulación, actualice la tabla del README: una prueba lo exige para cuatro cifras de ahorro, la reducción C.1 y el conteo de anclas (el rango de sensibilidad y las cifras de los pilotos se revisan a mano).
4. Revise que `git status` no incluya `resultados/`, `.env` ni claves.
   - Dos pruebas se omiten salvo que estén disponibles las piezas opcionales: el núcleo PESD (`MODEC_CE_PESD_SRC`) y el paquete MODEC original (`MODEC_CE_MODEC_SRC`). Ninguna de las dos forma parte de este repositorio.
5. Abra la solicitud de integración con el problema, el cambio y la salida de las pruebas.

## Licencia de las contribuciones

Las contribuciones se aceptan bajo la Licencia Apache 2.0 (sección 5 de `LICENSE`).
