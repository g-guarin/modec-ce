# Seguridad

## Reportar una vulnerabilidad

No la describa en una incidencia pública. Use el reporte privado de GitHub (pestaña **Security → Report a vulnerability**). Indique:
- el módulo afectado;
- la garantía que se rompe (integridad de la cadena, fallo cerrado, fuga de claves o de contenido);
- un caso mínimo, sin claves reales.

## Modelo de amenaza

Quien tiene incentivo para inflar una medición de ahorro es, normalmente, **quien cobra por haberla conseguido**: una consultoría que factura una optimización, un proveedor que anuncia una reducción de gasto, un autor que publica una cifra. No hace falta mala fe para que el número se desvíe —basta elegir la carga favorable, la franja tarifaria favorable, o descartar la corrida que salió mal—, y la parte que recibe la cifra hoy no tiene forma de auditarla.

Ese es el adversario para el que se construyó la cadena de evidencia. Qué encarece y qué no:

| Manipulación | ¿La detecta? | Cómo |
|---|---|---|
| Alterar una medición ya registrada | Sí | El digest del registro deja de coincidir |
| Borrar una corrida desfavorable | Sí | La secuencia tiene un salto y el enlace `hash_previo` se rompe |
| Reordenar registros | Sí | El orden forma parte de lo sellado |
| Añadir registros al final | Solo con ancla externa | Sin ancla, la cola no está acotada |
| Reescribir la bitácora entera y recalcular todo | Solo con clave HMAC o ancla externa | Sin ninguna de las dos, los digest son recalculables por cualquiera. La bitácora del 2026-11-22 sí tiene ancla (ver abajo) |
| Suplantar al firmante | Solo con clave HMAC, en modo estricto | Ver más abajo |
| Contar como cero un dato que el proveedor no informó | Sí | P2: queda AUSENTE y la corrida se detiene |
| Elegir una carga o una tarifa favorables | **No** | La bitácora las registra, no las juzga |

La última fila no se resuelve con criptografía: **MODEC-CE no puede decidir si la carga medida se parece a la suya**. Deja registrado con qué carga y con qué tarifa se midió, y permite correr el piloto con la suya. El README publica cómo cambia el ahorro según la forma de la carga.

## Límites declarados

- Según el autor, la cadena mínima integrada y el núcleo PESD **no han tenido revisión criptográfica por un especialista**.
- Sin un ancla externa, ninguna de las dos cadenas detecta que se trunque el final ni que se reescriba la cadena completa cuando no hay clave HMAC.
- **Ancla temporal, dónde la hay.** La bitácora del 2026-11-22 lleva un sello de tiempo RFC 3161 de FreeTSA sobre el digest de su último registro (`sello/piloto_deepseek_20261122_135846_5c1d7c/`), emitido el 22 de noviembre de 2026 a las 22:17:24 GMT. Acredita que esa cadena existía a más tardar en ese instante, y nada más: no acredita autoría ni que el contenido sea cierto. La del 2026-11-21 no tiene ancla, y el verificador lo dice. `verificar_independiente.py` comprueba que el ancla contiene el digest final de su cadena, pero no la firma de la autoridad: eso exige ASN.1 y la herramienta no tiene dependencias, así que lo declara como no comprobado y remite a `openssl ts -verify`.
- **La fecha del sello la declara el equipo que ejecuta el piloto**, no un tercero. Desde 0.2.0 viaja dentro del payload (con la versión y el commit), de modo que queda cubierta por el digest y no se puede cambiar sin romper la cadena; pero acredita una hora declarada, no certificada. El sello de tiempo RFC 3161 sobre el `digest` del último registro es lo que la vuelve verificable por terceros. La bitácora publicada con 0.1.0 no trae ninguno de esos campos, y el verificador lo declara como límite en su salida.
- **La verificación con clave es estricta a propósito**: exige `key_id` esperado y HMAC válido en todos los registros. Sin esa exigencia la autenticidad sería degradable, porque `key_id` va dentro del cuerpo digestado y podría quitarse de toda la cadena recalculando los digest. La clave es la declaración de qué firma se espera: si no se entrega, solo se comprueba integridad y una cadena sin firmas verifica igual.
- El presupuesto se comprueba después de cada llamada, así que puede excederse por el costo de una llamada como máximo; la cota preflight, que trata toda la entrada como no cacheada a la tarifa más alta, es la que impide arrancar un plan que no cabe.
- Las claves de los proveedores se leen solo de variables de entorno. `piloto_proveedor.ps1` las pide de forma protegida y las borra al terminar.
- La URL inicial solo puede ser `https://…` o `http://127.0.0.1:<puerto>`, y no se siguen redirecciones.
