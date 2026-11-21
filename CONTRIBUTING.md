# Cómo contribuir

## Reglas que no se negocian

1. **Mismo contenido entre disposiciones.** Una disposición nueva debe producir la misma `Peticion.huella_contenido` que las líneas base. Si cambia el contenido (como la compresión), se declara y se mide aparte.
2. **Ausente no es cero (P2).** Un campo de uso que el proveedor no informa se clasifica AUSENTE o VACIO y la medición queda NO_EVALUABLE. Nunca se rellena con 0.
3. **Dinero en `Decimal`.** Tarifas, cotas y costos se calculan con `decimal.Decimal`, nunca con `float`.
4. **Nada sensible en disco.** No se escriben claves, prompts ni respuestas en resultados ni en la bitácora; solo huellas SHA-256, conteos, latencias y costos.
5. **Procedencia declarada.** Toda cifra nueva dice si es ESTIMADA, COTA SUPERIOR, MEDIDA, DERIVADA o DECLARADA.
6. **Tarifas con fuente.** Un cambio en `datos/precios.json` cita la página oficial y la fecha de lectura.

## Flujo

1. Cree una rama descriptiva (`feat/…`, `fix/…`, `docs/…`).
2. Añada pruebas sin red en `tests/`.
3. Ejecute `python -B -m unittest discover -s tests`. Si cambian las cifras de la simulación, actualice la tabla del README: una prueba lo exige.
4. Revise que `git status` no incluya `resultados/`, `.env` ni claves.
5. Abra la solicitud de integración con el problema, el cambio y la salida de las pruebas.

## Licencia de las contribuciones

Las contribuciones se aceptan bajo la Licencia Apache 2.0 (sección 5 de `LICENSE`).
